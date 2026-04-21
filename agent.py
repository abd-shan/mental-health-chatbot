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
        # هدف النظام (Setpoint): الهدوء النفسي الرقمي
        self.target_sentiment = 1.0 

    def _monitor_sentiment(self, text: str) -> float:
        """
        Sensor: مستشعر لتحويل النص إلى قيمة عددية (Sentiment Score).
        هنا نمثل الـ Process Variable (PV).
        """
        negative_indicators = ["حزين", "قلق", "متوتر", "ضيق", "خائف", "تعبان"]
        score = 1.0
        for word in negative_indicators:
            if word in text:
                score -= 0.2
        return max(score, 0.0)

    def _verify_output(self, ai_response: str) -> bool:
        """
        Feedback Loop: مراجعة المخرجات قبل إرسالها (Guardrail).
        التأكد من أن الرد لا يحتوي على تشخيص طبي أو تحريض.
        """
        forbidden_patterns = ["أشخص حالتك بـ", "مرضك هو", "انتحار", "أذى"]
        return not any(pattern in ai_response for pattern in forbidden_patterns)

    def chat(self, user_input: str, patient_profile: Optional[dict] = None) -> dict:
        # 1. Measurement (Sensor)
        current_sentiment = self._monitor_sentiment(user_input)
        
        # 2. Comparison (Error Calculation)
        error = self.target_sentiment - current_sentiment
        
        # 3. Decision Logic (Controller)
 
        control_instruction = ""
        if error > 0.4:
            control_instruction = "\nتنبيه للنظام: المستخدم يمر بحالة توتر عالية. ركز على تقنيات التنفس والهدوء فوراً."

        dynamic_context = build_dynamic_context(patient_profile)
        self.messages.append(HumanMessage(content=user_input))

        active_prompt = [
            self.messages[0], 
            SystemMessage(content=dynamic_context + control_instruction)
        ] + self.messages[-10:]

        # 4. Action (Actuator)
        intent = detect_intent(user_input)
        try:
            if intent in ["support", "booking"]:
                result = agent_executor.invoke({"messages": active_prompt})
                ai_content = result["messages"][-1].content
            else:
                response = llm.invoke(active_prompt)
                ai_content = response.content
            
            # 5. Output Verification (Feedback)
            if not self._verify_output(ai_content):
                ai_content = "أنا هنا لأسمعك وأدعمك، ولكن يرجى العلم أنني لا أستطيع تقديم تشخيصات طبية. كيف يمكننا التركيز على شعورك الآن؟"

        except Exception as e:
            logger.error(f"Control Loop Error: {e}")
            ai_content = "عذراً، أحتاج لحظة لمعالجة الطلب."

        self.messages.append(AIMessage(content=ai_content))
        
        # Stability Control: الحفاظ على استقرار الذاكرة (Memory Buffer)
        self.messages = [self.messages[0]] + self.messages[-12:]

        return {
            "response": ai_content,
            "status": {
                "sentiment_score": current_sentiment,
                "error_level": round(error, 2),
                "intent": intent
            }
        }
