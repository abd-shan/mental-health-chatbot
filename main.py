from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv
import uuid
import logging
import os

from agent import ConversationController

# ===============================
# Environment
# ===============================

load_dotenv()

# ===============================
# Logging
# ===============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ===============================
# App Initialization
# ===============================

app = FastAPI(
    title="Mental Health Chatbot",
    docs_url=None,     # إخفاء docs في التجربة العامة
    redoc_url=None
)

# ===============================
# Middleware (مهم جداً على Railway)
# ===============================

# دعم Reverse Proxy (Railway)

# CORS (يمكن تقييده لاحقاً)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# Static & Templates
# ===============================

BASE_DIR = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ===============================
# Session Store (مؤقت للتجربة)
# ===============================

sessions: dict[str, ConversationController] = {}
MAX_SESSIONS = 500  # منع استهلاك الذاكرة

def get_or_create_session(session_id: str) -> ConversationController:
    if session_id not in sessions:
        if len(sessions) > MAX_SESSIONS:
            logger.warning("Session limit reached. Clearing memory.")
            sessions.clear()
        sessions[session_id] = ConversationController()
    return sessions[session_id]

# ===============================
# Models
# ===============================

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

# ===============================
# Routes
# ===============================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, response: Response):

    session_id = request.cookies.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,     # مهم مع HTTPS
            samesite="lax"
        )

    get_or_create_session(session_id)

    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, request: Request, response: Response):

    session_id = request.cookies.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax"
        )

    controller = get_or_create_session(session_id)

    try:
        response_text = controller.chat(req.message)
    except Exception as e:
        logger.exception("Chat processing failed")
        raise HTTPException(
            status_code=500,
            detail="حدث خطأ مؤقت في المعالجة. حاول مرة أخرى."
        )

    return ChatResponse(response=response_text)

# ===============================
# Local Run (للجهاز فقط)
# ===============================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
