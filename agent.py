import os
import json
import random
import string
from datetime import datetime, timedelta
from typing import List, Optional
import logging

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
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
# Tools
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
    model="deepseek/deepseek-chat",
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
# Agent
# ==============================

agent_executor = create_agent(
    model=llm,
    tools=tools,
    system_prompt=BASE_SYSTEM_PROMPT,
)

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
# Controller
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
        self.last_output = 0.0
        
        # معاملات التحكم PID (قابلة للضبط)
        self.Kp = 1.2   # Proportional Gain
        self.Ki = 0.3   # Integral Gain
        self.Kd = 0.5   # Derivative Gain
        self.dt = 1.0   # فترة العينة (افتراضية 1 لأن كل رسالة هي خطوة)
        
        # معامل المرشح الرقمي (Low-pass Filter) لتنعيم PV
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
        # التناسبي (Proportional)
        P = self.Kp * error
        
        # التراكمي (Integral) مع مقاومة التشبع (Anti-windup)
        self.integral += error * self.dt
        # تحديد حدود التراكم لتجنب التشبع
        self.integral = max(-2.0, min(self.integral, 2.0))
        I = self.Ki * self.integral
        
        # التفاضلي (Derivative)
        derivative = (error - self.prev_error) / self.dt
        D = self.Kd * derivative
        
        # حفظ الخطأ السابق
        self.prev_error = error
        
        # إشارة التحكم النهائية
        control_signal = P + I + D
        return control_signal

    def chat(self, user_input: str, patient_profile: Optional[dict] = None, medical_context: Optional[dict] = None) -> dict:
        # 1. القياس الخام (Raw Measurement)
        raw_sentiment = self._monitor_sentiment(user_input)
        
        # 2. تطبيق المرشح الرقمي للحصول على PV الحقيقي (مستقر)
        current_sentiment = self._apply_low_pass_filter(raw_sentiment)
        
        # 3. حساب الخطأ (Error = SP - PV)
        error = self.target_sentiment - current_sentiment
        
        # 4. حساب إشارة التحكم PID
        control_signal = self._pid_control(error)
        
        # 5. بناء تعليمات التحكم بناءً على إشارة PID
        control_instruction = ""
        if error > 0.35:
            control_instruction = "\n[تحكم PID]: حالة توتر عالية. استخدم تقنيات التنفس والتهدئة الفورية."
        elif error > 0.15:
            control_instruction = "\n[تحكم PID]: توتر متوسط. حافظ على نبرة داعمة وقدم تمارين بسيطة."
        else:
            control_instruction = "\n[تحكم PID]: حالة مستقرة. قدم استشارات عادية."

        # يمكن إضافة تأثير control_signal على اختيار نوع الرد أو على معامل temperature
        # مثلاً: إذا كان control_signal كبيراً نزيد من التركيز على التعاطف.
        
        # 6. بناء السياق وإرسال الطلب للنموذج اللغوي
        dynamic_context = build_dynamic_context(patient_profile, medical_context)
        self.messages.append(HumanMessage(content=user_input))

        active_prompt = [
            self.messages[0], 
            SystemMessage(content=dynamic_context + control_instruction)
        ] + self.messages[-10:]

        intent = detect_intent(user_input)
        try:
            if intent in ["support", "booking"]:
                result = agent_executor.invoke({"messages": active_prompt})
                ai_content = result["messages"][-1].content
            else:
                response = llm.invoke(active_prompt)
                ai_content = response.content
            
            if not self._verify_output(ai_content):
                ai_content = "أنا هنا لأسمعك وأدعمك، ولكن يرجى العلم أنني لا أستطيع تقديم تشخيصات طبية. كيف يمكننا التركيز على شعورك الآن؟"

        except Exception as e:
            logger.error(f"Control Loop Error: {e}")
            ai_content = "عذراً، أحتاج لحظة لمعالجة الطلب."

        self.messages.append(AIMessage(content=ai_content))
        self.messages = [self.messages[0]] + self.messages[-12:]

        # 7. إرجاع البيانات مع قيم حقيقية بعد المعالجة
        return {
            "response": ai_content,
            "status": {
                "sentiment_score": round(current_sentiment, 3),      # PV بعد المرشح
                "error_level": round(error, 3),                      # الخطأ الحقيقي
                "control_signal": round(control_signal, 3),          # إشارة PID
                "intent": intent
            }
        }
