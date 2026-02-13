from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uuid
from dotenv import load_dotenv

from agent import ConversationController

load_dotenv()

app = FastAPI(title="Mental Health Chatbot")

# إعداد الملفات الثابتة والقوالب
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# تخزين الجلسات (في الإنتاج استخدم قاعدة بيانات)
sessions: dict[str, ConversationController] = {}

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, response: Response):
    # التحقق من وجود معرف جلسة في الكوكيز
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id, httponly=True)
    # إنشاء وحدة تحكم للجلسة إذا لم تكن موجودة
    if session_id not in sessions:
        sessions[session_id] = ConversationController()
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id, httponly=True)
        sessions[session_id] = ConversationController()
    else:
        if session_id not in sessions:
            sessions[session_id] = ConversationController()

    controller = sessions[session_id]
    response_text = controller.chat(req.message)
    return ChatResponse(response=response_text)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)