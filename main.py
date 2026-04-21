from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional , Any
import uuid
import logging

from agent import ConversationController

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mental Health Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")

sessions = {}

# ===============================
# Request Models
# ===============================

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    patient_profile: Optional[dict] = None
    medical_context: Optional[dict] = None


class ChatResponse(BaseModel):
    response: str
    status: Optional[Any] = None

# ===============================
# Session Manager
# ===============================

def get_or_create_session(session_id: str):
    if session_id not in sessions:
        sessions[session_id] = ConversationController()
    return sessions[session_id]

# ===============================
# Routes
# ===============================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    controller = get_or_create_session(conversation_id)

    try:
        result = controller.chat(
            user_input=req.message,
            patient_profile=req.patient_profile,
            medical_context=req.medical_context
        )
        
        logger.info(f"Control Metrics: {result.get('status')}")
        
        return ChatResponse(
            response=result["response"], 
            status=result.get("status")
        )
        
    except Exception:
        logger.exception("Chat failed")
        raise HTTPException(status_code=500, detail="خطأ في نظام التحكم")

# ===============================
# Local Run
# ===============================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
