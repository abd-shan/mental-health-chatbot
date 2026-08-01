import os
from typing import Any, List, Mapping, Optional, Sequence
import logging
import threading
import time

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

from catalog import platform_catalog
from prompting import TurnPlan, build_pre_query, infer_turn_plan
from summarization import SUMMARY_SYSTEM_PROMPT, build_summary_payload

# ==============================
# Environment
# ==============================

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Aoun Mental Health Chatbot")
OPENROUTER_SUMMARY_MODEL = os.getenv("OPENROUTER_SUMMARY_MODEL", OPENROUTER_MODEL)

# ==============================
# Logging
# ==============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================
# LLM
# ==============================

def create_llm(model: str, temperature: float) -> Optional[ChatOpenAI]:
    """Create the OpenRouter-backed LangChain client when configured."""
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY is not set; fallback responses are enabled")
        return None

    headers = {"X-Title": OPENROUTER_APP_NAME}
    if OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL

    return ChatOpenAI(
        model=model,
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        temperature=temperature,
        timeout=30,
        max_retries=1,
        default_headers=headers,
    )


llm = create_llm(OPENROUTER_MODEL, temperature=0.3)
summary_llm = (
    llm
    if OPENROUTER_SUMMARY_MODEL == OPENROUTER_MODEL
    else create_llm(OPENROUTER_SUMMARY_MODEL, temperature=0.1)
)


def summarize_conversation(
    existing_summary: Optional[str],
    messages: Sequence[Mapping[str, Any]],
) -> str:
    """Create a durable summary that the main backend can persist."""
    if not summary_llm:
        raise RuntimeError("OpenRouter is not configured")

    response = summary_llm.invoke(
        [
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=build_summary_payload(existing_summary, messages)),
        ]
    )
    content = response.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The summary model returned an empty response")
    summary = content.strip()
    if len(summary) > 6000:
        raise RuntimeError("The summary model exceeded the output limit")
    return summary

CRISIS_INDICATORS = (
    "أريد أن أموت",
    "اريد ان اموت",
    "أفكر بالانتحار",
    "افكر بالانتحار",
    "سأنتحر",
    "سانتحر",
    "أؤذي نفسي",
    "اؤذي نفسي",
    "إيذاء نفسي",
    "ايذاء نفسي",
    "قتل نفسي",
    "بقتل نفسي",
    "أنهي حياتي",
    "انهي حياتي",
    "ما أبغى أعيش",
    "ما ابغى اعيش",
    "ما عاد أبغى أعيش",
    "ما عاد ابغى اعيش",
    "ودي أموت",
    "ودي اموت",
    "بنتحر",
    "suicide",
    "kill myself",
    "hurt myself",
    "self harm",
)


def detect_crisis(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(indicator in normalized for indicator in CRISIS_INDICATORS)


def crisis_response() -> str:
    return (
        "سلامتك أهم شيء الآن. إذا كنت على وشك إيذاء نفسك أو لديك وسيلة قريبة، "
        "ابتعد عنها واتصل بخدمات الطوارئ المحلية فوراً أو توجّه إلى أقرب قسم طوارئ. "
        "في السعودية يمكنك الاتصال بـ997 أو 999، وبـ911 حيث تكون الخدمة متاحة. "
        "اطلب من شخص تثق به أن يبقى معك الآن، ولا تبقَ وحدك. "
        "هل أنت في خطر فوري الآن، وهل يوجد شخص قريب يمكنه الوصول إليك؟"
    )

# ==============================
# Controller (PID + Low-pass Filter)
# ==============================

class ConversationController:
    def __init__(self):
        self._lock = threading.Lock()
        self.messages: List[BaseMessage] = []
        self.target_sentiment = 1.0
        
        # === متغيرات PID والمرشحات ===
        self.prev_error = 0.0
        self.integral = 0.0
        self.filtered_sentiment = 1.0  # قيمة PV بعد المرشح الرقمي
        
        # معاملات التحكم PID
        self.Kp = 1.2
        self.Ki = 0.3
        self.Kd = 0.5
        self.dt = 1.0
        
        # معامل المرشح الرقمي (Low-pass Filter)
        self.ALPHA_FILTER = 0.2

    def _monitor_sentiment(self, text: str) -> float:
        """مستشعر رقمي خام (Raw Sensor)"""
        negative_indicators = ["حزين", "قلق", "متوتر", "ضيق", "خائف", "تعبان", "غاضب", "مكتئب"]
        positive_indicators = ["سعيد", "مرتاح", "ممتن", "هادئ", "متفائل"]
        score = 1.0
        
        for word in negative_indicators:
            if word in text:
                score -= 0.15
        for word in positive_indicators:
            if word in text:
                score += 0.1
                
        return max(0.0, min(score, 1.0))

    def _apply_low_pass_filter(self, raw_value: float) -> float:
        """مرشح رقمي من الدرجة الأولى (Exponential Filter) لتنعيم القراءات"""
        self.filtered_sentiment = self.ALPHA_FILTER * raw_value + (1 - self.ALPHA_FILTER) * self.filtered_sentiment
        return self.filtered_sentiment

    def _pid_control(self, error: float) -> float:
        """حساب إشارة التحكم (Control Signal) باستخدام PID"""
        P = self.Kp * error
        
        self.integral += error * self.dt
        self.integral = max(-2.0, min(self.integral, 2.0))  # Anti-windup
        I = self.Ki * self.integral
        
        derivative = (error - self.prev_error) / self.dt
        D = self.Kd * derivative
        
        self.prev_error = error
        control_signal = P + I + D
        return control_signal

    def _generate_fallback_response(self, turn_plan: TurnPlan) -> str:
        """Safe, intent-aware response when the LLM provider is unavailable."""
        if turn_plan.response_mode == "booking_preparation":
            return (
                "أستطيع مساعدتك في الاستعداد للحجز، لكن لا يمكنني تأكيد موعد من "
                "داخل المحادثة حالياً. هل تبحث عن أخصائي نفسي أم جلسة دعم عامة؟"
            )
        if turn_plan.response_mode == "safe_medication_boundary":
            return (
                "لا أستطيع تحديد دواء أو جرعة أو تغيير علاج. الأفضل توجيه هذا "
                "السؤال إلى طبيبك أو صيدلي مؤهل، خصوصاً إذا كان مرتبطاً بوصفة حالية."
            )
        if turn_plan.response_mode == "psychoeducation":
            return (
                "تعذر الوصول إلى مصدر الإجابة الذكي حالياً، لذلك لا أريد تخمين "
                "معلومة نفسية قد تكون غير دقيقة. يمكنك إعادة المحاولة بعد قليل."
            )
        if turn_plan.emotional_intensity == "high":
            return "أشعر أنك تمر بوقت صعب جداً الآن. أنا هنا معك. دعنا نأخذ لحظة للتنفس: خذ شهيقاً عميقاً... احبسه قليلاً... والآن أخرج الزفير ببطء. أنا أسمعك."
        if turn_plan.emotional_intensity == "elevated":
            return "يبدو أن هناك شيئاً يزعجك. أود أن أفهم أكثر. هل يمكنك أن تخبرني ما الذي يدور في بالك الآن؟"
        return "شكراً لمشاركتك. أنا هنا لدعمك. كيف يمكنني مساعدتك اليوم؟"

    def _verify_output(self, ai_response: str) -> bool:
        """Reject obvious diagnosis, medication, or fake-action claims."""
        if not ai_response or len(ai_response.strip()) < 2:
            return False
        forbidden_patterns = [
            "أشخص حالتك",
            "مرضك هو",
            "أنت مصاب بـ",
            "أوقف دواءك",
            "ابدأ بتناول",
            "زد جرعتك",
            "خفّض جرعتك",
            "تم حجز موعدك",
            "موعدك مؤكد",
        ]
        return not any(pattern in ai_response for pattern in forbidden_patterns)

    @staticmethod
    def _build_history(recent_messages: Optional[Sequence[Mapping[str, Any]]]) -> List[BaseMessage]:
        history: List[BaseMessage] = []
        for message in recent_messages or []:
            role = message.get("role")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            if role == "user":
                history.append(HumanMessage(content=content))
            elif role == "assistant":
                history.append(AIMessage(content=content))
        return history[-10:]

    def chat(
        self,
        user_input: str,
        patient_profile: Optional[dict] = None,
        medical_context: Optional[dict] = None,
        conversation_summary: Optional[str] = None,
        recent_messages: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> dict:
        with self._lock:
            return self._chat(
                user_input,
                patient_profile,
                medical_context,
                conversation_summary,
                recent_messages,
            )

    def _chat(
        self,
        user_input: str,
        patient_profile: Optional[dict] = None,
        medical_context: Optional[dict] = None,
        conversation_summary: Optional[str] = None,
        recent_messages: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> dict:
        if detect_crisis(user_input):
            response = crisis_response()
            self.messages.append(HumanMessage(content=user_input))
            self.messages.append(AIMessage(content=response))
            self.messages = self.messages[-12:]
            return {
                "response": response,
                "status": {
                    "sentiment_score": 0.0,
                    "error_level": 1.0,
                    "control_signal": 1.0,
                    "intent": "crisis",
                    "risk_level": "urgent",
                },
            }

        # 1. القياس الخام
        raw_sentiment = self._monitor_sentiment(user_input)
        
        # 2. تطبيق المرشح الرقمي (PV)
        current_sentiment = self._apply_low_pass_filter(raw_sentiment)
        
        # 3. حساب الخطأ
        error = self.target_sentiment - current_sentiment
        
        # 4. إشارة PID
        control_signal = self._pid_control(error)
        
        # 5. بناء خطة الدور وطبقة ما قبل الاستعلام
        turn_plan = infer_turn_plan(user_input, raw_sentiment)
        catalog_context = None
        if turn_plan.intent in {"booking", "education", "support"}:
            catalog_context = platform_catalog.get_relevant_context(
                user_input,
                turn_plan.intent,
            )
        system_content = build_pre_query(
            turn_plan=turn_plan,
            patient_profile=patient_profile,
            medical_context=medical_context,
            conversation_summary=conversation_summary,
            platform_catalog=catalog_context,
            smoothed_affect_score=current_sentiment,
        )
        user_message = HumanMessage(content=user_input)
        supplied_history = self._build_history(recent_messages)
        history = supplied_history if recent_messages is not None else self.messages[-10:]
        active_prompt = [SystemMessage(content=system_content)] + history + [user_message]

        ai_content = ""
        
        # 7. استدعاء LLM مع إعادة المحاولة
        max_retries = 2 if llm else 0
        llm_success = False
        for attempt in range(max_retries):
            try:
                response = llm.invoke(active_prompt)
                ai_content = response.content
                llm_success = True
                logger.info(f"LLM responded successfully on attempt {attempt+1}")
                break
            except Exception as e:
                logger.error(f"LLM call failed (attempt {attempt+1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    logger.warning("Switching to fallback response based on PID state.")
                    ai_content = self._generate_fallback_response(turn_plan)
                else:
                    time.sleep(0.8)

        if not llm:
            ai_content = self._generate_fallback_response(turn_plan)

        # 8. التحقق من المخرجات
        if llm_success and not self._verify_output(ai_content):
            logger.warning("LLM output was rejected by the output guard")
            ai_content = self._generate_fallback_response(turn_plan)

        # 9. تخزين الرد في الذاكرة
        self.messages.append(user_message)
        self.messages.append(AIMessage(content=ai_content))
        self.messages = self.messages[-12:]

        # 10. إرجاع النتيجة
        return {
            "response": ai_content,
            "status": {
                "sentiment_score": round(current_sentiment, 3),
                "error_level": round(error, 3),
                "control_signal": round(control_signal, 3),
                "intent": turn_plan.intent,
                "response_mode": turn_plan.response_mode,
                "emotional_intensity": turn_plan.emotional_intensity,
                "catalog_sources": (
                    catalog_context.get("sources", []) if catalog_context else []
                ),
                "risk_level": "none",
            }
        }
