from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Literal, Optional
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

load_dotenv()

from agent import (  # noqa: E402 - environment must be loaded first
    ConversationController,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_SUMMARY_MODEL,
    summarize_conversation,
)
from catalog import platform_catalog  # noqa: E402


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "development").lower()
ENABLE_TEST_UI = os.getenv(
    "ENABLE_TEST_UI", "false" if APP_ENV == "production" else "true"
).lower() == "true"
ENABLE_API_DOCS = os.getenv(
    "ENABLE_API_DOCS", "false" if APP_ENV == "production" else "true"
).lower() == "true"
AI_SERVICE_API_KEY = os.getenv("AI_SERVICE_API_KEY")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "1000"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    if APP_ENV == "production" and not AI_SERVICE_API_KEY:
        raise RuntimeError("AI_SERVICE_API_KEY is required in production")
    yield


app = FastAPI(
    title="Aoun AI Chat Service",
    version="1.1.0",
    description="Internal AI service for the Aoun mental-health support platform.",
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
    lifespan=lifespan,
)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Service-Token", "X-Request-ID"],
    )

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
if ENABLE_TEST_UI:
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

sessions: dict[str, tuple[ConversationController, float]] = {}
sessions_lock = threading.Lock()


class ConversationMessage(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("id", "content")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must contain text")
        return value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    conversation_summary: Optional[str] = Field(default=None, max_length=6000)
    recent_messages: Optional[list[ConversationMessage]] = Field(default=None, max_length=12)
    patient_profile: Optional[dict[str, Any]] = None
    medical_context: Optional[dict[str, Any]] = None

    @field_validator("message")
    @classmethod
    def message_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must contain text")
        return value

    @field_validator("conversation_id")
    @classmethod
    def normalize_conversation_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("conversation_id must contain text")
        return value


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    status: Optional[dict[str, Any]] = None


class SummaryRequest(BaseModel):
    existing_summary: Optional[str] = Field(default=None, max_length=6000)
    messages: list[ConversationMessage] = Field(min_length=1, max_length=12)


class SummaryResponse(BaseModel):
    conversation_id: str
    summary: str
    covered_message_ids: list[str]


class HealthResponse(BaseModel):
    status: str
    provider: str
    chat_model: str
    summary_model: str
    llm_configured: bool
    platform_api_configured: bool


def get_or_create_session(session_id: str) -> ConversationController:
    now = time.monotonic()
    with sessions_lock:
        expired_ids = [
            key
            for key, (_, last_seen) in sessions.items()
            if now - last_seen > SESSION_TTL_SECONDS
        ]
        for key in expired_ids:
            sessions.pop(key, None)

        if session_id in sessions:
            controller, _ = sessions[session_id]
            sessions[session_id] = (controller, now)
            return controller

        if len(sessions) >= MAX_SESSIONS:
            oldest_id = min(sessions, key=lambda key: sessions[key][1])
            sessions.pop(oldest_id, None)

        controller = ConversationController()
        sessions[session_id] = (controller, now)
        return controller


def purge_session(session_id: str) -> None:
    with sessions_lock:
        sessions.pop(session_id, None)


def verify_service_token(x_service_token: Optional[str] = Header(default=None)) -> None:
    """Protect backend-to-AI routes when a service secret is configured."""
    if AI_SERVICE_API_KEY and (
        not x_service_token
        or not secrets.compare_digest(x_service_token, AI_SERVICE_API_KEY)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def read_root(request: Request):
    if not ENABLE_TEST_UI:
        raise HTTPException(status_code=404, detail="Test UI is disabled")
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_endpoint() -> HealthResponse:
    return HealthResponse(
        status="ok" if OPENROUTER_API_KEY else "degraded",
        provider="openrouter",
        chat_model=OPENROUTER_MODEL,
        summary_model=OPENROUTER_SUMMARY_MODEL,
        llm_configured=bool(OPENROUTER_API_KEY),
        platform_api_configured=platform_catalog.configured,
    )


@app.get("/health/live", tags=["health"])
async def liveness_endpoint() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
async def readiness_endpoint():
    ready = bool(OPENROUTER_API_KEY) and (
        APP_ENV != "production" or bool(AI_SERVICE_API_KEY)
    )
    payload = {
        "status": "ready" if ready else "not_ready",
        "llm_configured": bool(OPENROUTER_API_KEY),
        "service_auth_configured": bool(AI_SERVICE_API_KEY),
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


@app.get(
    "/api/v1/catalog/status",
    dependencies=[Depends(verify_service_token)],
    tags=["catalog"],
)
async def catalog_status_endpoint() -> dict[str, Any]:
    return platform_catalog.status()


@app.post(
    "/api/v1/catalog/refresh",
    dependencies=[Depends(verify_service_token)],
    tags=["catalog"],
)
async def catalog_refresh_endpoint():
    available = await run_in_threadpool(platform_catalog.refresh, force=True)
    payload = platform_catalog.status()
    if not available:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )
    return payload


async def process_chat(req: ChatRequest) -> ChatResponse:
    conversation_id = req.conversation_id or str(uuid.uuid4())
    controller = get_or_create_session(conversation_id)

    try:
        result = await run_in_threadpool(
            controller.chat,
            user_input=req.message,
            patient_profile=req.patient_profile,
            medical_context=req.medical_context,
            conversation_summary=req.conversation_summary,
            recent_messages=(
                [message.model_dump() for message in req.recent_messages]
                if req.recent_messages is not None
                else None
            ),
        )
        logger.info("Control metrics: %s", result.get("status"))
        return ChatResponse(
            conversation_id=conversation_id,
            response=result["response"],
            status=result.get("status"),
        )
    except Exception:
        logger.exception("Chat failed")
        raise HTTPException(status_code=500, detail="تعذر معالجة الرسالة حالياً")


@app.post("/chat", response_model=ChatResponse, include_in_schema=False)
async def legacy_chat_endpoint(req: ChatRequest) -> ChatResponse:
    if not ENABLE_TEST_UI:
        raise HTTPException(status_code=404, detail="Test UI is disabled")
    return await process_chat(req)


@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    dependencies=[Depends(verify_service_token)],
    tags=["chat"],
)
async def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """Generate a response using the backend-owned summary and recent messages."""
    return await process_chat(req)


@app.post(
    "/api/v1/conversations/{conversation_id}/summary",
    response_model=SummaryResponse,
    dependencies=[Depends(verify_service_token)],
    tags=["conversations"],
)
async def summarize_endpoint(
    conversation_id: str,
    req: SummaryRequest,
) -> SummaryResponse:
    try:
        messages = [message.model_dump() for message in req.messages]
        summary = await run_in_threadpool(
            summarize_conversation,
            req.existing_summary,
            messages,
        )
        return SummaryResponse(
            conversation_id=conversation_id,
            summary=summary,
            covered_message_ids=[message.id for message in req.messages],
        )
    except RuntimeError as exc:
        logger.warning("Summary generation unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Summary model is unavailable")
    except Exception:
        logger.exception("Conversation summary failed")
        raise HTTPException(status_code=500, detail="تعذر تلخيص المحادثة حالياً")


@app.delete(
    "/api/v1/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_service_token)],
    tags=["conversations"],
)
async def purge_conversation_endpoint(conversation_id: str) -> Response:
    """Idempotently purge the AI service's ephemeral state for a conversation."""
    purge_session(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Backward-compatible import for code that still imports main.app1.
app1 = app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
