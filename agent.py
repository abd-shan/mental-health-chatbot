import os
import json
import random
import string
from datetime import datetime, timedelta
from typing import List, Optional
import logging
import time

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
# Agent معطّل حالياً - نستخدم الاستدعاء المباشر
# from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

# ==============================
# Environment
# ==============================

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is not set")

# ==============================
# Logging
# ==============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================
# Tools (محتفظة بها للاستخدام المستقبلي)
# ==============================

@tool
def generate_session_id() -> str:
    """Generate secure session ID."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(24))


@tool
def breathing_exercise() -> str:
    """Guide user through a short breathing exercise."""
    return (
        "لنأخذ لحظة هدوء.\n"
        "1. خذ نفساً عميقاً لمدة 4 ثوانٍ.\n"
        "2. احبس النفس 4 ثوانٍ.\n"
        "3. ازفر ببطء لمدة 6 ثوانٍ.\n"
        "كرر ذلك 4 مرات."
    )


@tool
def schedule_session(name: str, days_from_now: int = 1) -> str:
    """Simulate scheduling a therapy session."""
    date = datetime.utcnow() + timedelta(days=days_from_now)
    booking = {
        "client": name,
        "scheduled_at": date.isoformat(),
        "status": "confirmed"
    }
    return json.dumps(booking, ensure_ascii=False)

tools = [generate_session_id, breathing_exercise, schedule_session]

# ==============================
# LLM
# ==============================

llm = ChatOpenAI(
    model="deepseek/deepseek-chat",  # يمكن تغييره إلى "google/gemini-flash-1.5" إن كان مجانياً
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    temperature=0.3,
)

# ==============================
# Base Prompt
# ==============================

BASE_SYSTEM_PROMPT = """
أنت مساعد متخصص في الدعم النفسي ضمن منصة عون.

الهوية:
- التطبيق من تطوير فريق منصة عون.
- المطور التقني: المهندس عبدالقادر الشنبور.

المبادئ:
- قدم دعماً نفسياً هادئاً.
- لا تقدم تشخيصاً طبياً.
- عزز القيم الأخلاقية.
- لا تشجع السلوك الضار.
- كن مختصراً وواضحاً.
"""

# ==============================
# Dynamic Context Builder
# ==============================

def build_dynamic_context(patient_profile=None, medical_context=None):

    name = "غير معروف"
    age = "غير متوفر"
    gender = "غير محدد"

    history = "لا توجد معلومات طبية متاحة"
    last_visit = "غير معروفة"

    if patient_profile:
        name = patient_profile.get("name") or "غير معروف"
        age = patient_profile.get("age") or "غير متوفر"
        gender = patient_profile.get("gender") or "غير محدد"

    if medical_context:
        history = medical_context.get("history") or "لا توجد معلومات طبية متاحة"
        last_visit = medical_context.get("last_visit") or "غير معروفة"

    return f"""
بيانات المستخدم:
الاسم: {name}
العمر: {age}
الجنس: {gender}

السجل الطبي:
{history}

آخر مراجعة:
{last_visit}

إذا كانت البيانات ناقصة:
- تعامل بمرونة
- لا تفترض معلومات غير موجودة
"""

# ==============================
# Intent Detection
# ==============================

def detect_intent(text: str) -> str:
    text = text.lower()

    if any(word in text for word in ["اشرح", "ما هو", "تعريف"]):
        return "education"

    elif any(word in text for word in ["متوتر", "قلق", "حزين", "ضيق"]):
        return "support"

    elif any(word in text for word in ["احجز", "جلسة", "موعد"]):
        return "booking"

    return "casual"

# ==============================
# Controller (PID + Low-pass Filter)
# ==============================

class ConversationController:
    def __init__(self):
        self.messages: List[BaseMessage] = []
        self.messages.append(SystemMessage(content=BASE_SYSTEM_PROMPT))
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

    def _generate_fallback_response(self, user_input: str, sentiment: float, error: float) -> str:
        """وضع المحاكاة: ردود مبنية على منطق التحكم فقط (في حال تعذر الاتصال بـ LLM)."""
        if error > 0.35:
            return "أشعر أنك تمر بوقت صعب جداً الآن. أنا هنا معك. دعنا نأخذ لحظة للتنفس: خذ شهيقاً عميقاً... احبسه قليلاً... والآن أخرج الزفير ببطء. أنا أسمعك."
        elif error > 0.15:
            return "يبدو أن هناك شيئاً يزعجك. أود أن أفهم أكثر. هل يمكنك أن تخبرني ما الذي يدور في بالك الآن؟"
        else:
            return "شكراً لمشاركتك. أنا هنا لدعمك. كيف يمكنني مساعدتك اليوم؟"

    def _verify_output(self, ai_response: str) -> bool:
        """التحقق من سلامة الرد"""
        if not ai_response or len(ai_response.strip()) < 2:
            return False
        forbidden_patterns = ["أشخص حالتك بـ", "مرضك هو", "انتحار", "أذى"]
        return not any(pattern in ai_response for pattern in forbidden_patterns)

    def chat(self, user_input: str, patient_profile: Optional[dict] = None, medical_context: Optional[dict] = None) -> dict:
        # 1. القياس الخام
        raw_sentiment = self._monitor_sentiment(user_input)
        
        # 2. تطبيق المرشح الرقمي (PV)
        current_sentiment = self._apply_low_pass_filter(raw_sentiment)
        
        # 3. حساب الخطأ
        error = self.target_sentiment - current_sentiment
        
        # 4. إشارة PID
        control_signal = self._pid_control(error)
        
        # 5. تعليمات التحكم
        control_instruction = ""
        if error > 0.35:
            control_instruction = "\n[تحكم PID]: حالة توتر عالية جداً. استخدم تمارين تنفس فورية وكن داعماً بقوة."
        elif error > 0.15:
            control_instruction = "\n[تحكم PID]: توتر ملحوظ. استخدم أسلوباً لطيفاً واطرح أسئلة مفتوحة للتفريغ."
        else:
            control_instruction = "\n[تحكم PID]: الحالة مستقرة. قدم دعماً روتينياً أو استفسر عن الاحتياجات."

        # 6. بناء السياق
        dynamic_context = build_dynamic_context(patient_profile, medical_context)
        self.messages.append(HumanMessage(content=user_input))

        system_content = dynamic_context + control_instruction
        active_prompt = [SystemMessage(content=system_content)] + self.messages[-10:]

        intent = detect_intent(user_input)
        ai_content = ""
        
        # 7. استدعاء LLM مع إعادة المحاولة
        max_retries = 2
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
                    ai_content = self._generate_fallback_response(user_input, current_sentiment, error)
                else:
                    time.sleep(0.8)

        # 8. التحقق من المخرجات
        if llm_success and not self._verify_output(ai_content):
            ai_content = "أنا هنا لأسمعك وأدعمك، ولكن يرجى العلم أنني لا أستطيع تقديم تشخيصات طبية. كيف يمكننا التركيز على شعورك الآن؟"

        # 9. تخزين الرد في الذاكرة
        self.messages.append(AIMessage(content=ai_content))
        self.messages = [self.messages[0]] + self.messages[-12:]

        # 10. إرجاع النتيجة
        return {
            "response": ai_content,
            "status": {
                "sentiment_score": round(current_sentiment, 3),
                "error_level": round(error, 3),
                "control_signal": round(control_signal, 3),
                "intent": intent
            }
        }
