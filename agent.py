import os
import json
import random
import string
from datetime import datetime, timedelta
from typing import List
import logging

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

# تحميل متغيرات البيئة
load_dotenv()

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================
# الأدوات (Tools)
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

# قائمة الأدوات الأساسية
tools = [generate_session_id, breathing_exercise, schedule_session]

# ==============================
# إعداد النموذج اللغوي (LLM)
# ==============================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is not set")

llm = ChatOpenAI(
    model="deepseek/deepseek-chat",
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    temperature=0.3,
)


# ==============================
# SYSTEM PROMPT مُحسّن
# ==============================

SYSTEM_PROMPT = """
أنت مساعد متخصص في المحادثات النفسية والدعم العاطفي.
المبادئ التوجيهية:
- كن فضولياً واطرح أسئلة استكشافية قبل اللجوء إلى الأدوات.
- لا تفترض القلق أو التوتر مباشرة؛ افهم السياق أولاً.
- إذا كان السؤال تعليمياً (مثلاً "ما هو القلق؟")، قدم شرحاً وافياً دون استخدام أدوات.
- الأدوات (مثل تمارين التنفس أو حجز الجلسات) هي وسيلة ثانوية؛ المحادثة هي الأساس.
- حافظ على نبرة هادئة ومتعاطفة.
- لا تقدم تشخيصات طبية.
"""

# ==============================
# إنشاء agent_executor باستخدام create_agent
# ==============================

agent_executor = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
)

# ==============================
# دالة كشف النية (Intent Router)
# ==============================

def detect_intent(text: str) -> str:
    """تحديد نية المستخدم بناءً على النص."""
    text = text.lower()
    if any(word in text for word in ["اشرح", "ما هو", "ماهي", "تعريف", "شرح"]):
        return "education"
    elif any(word in text for word in ["دعم", "متوتر", "قلق", "حزين", "تعاسة", "ضيق"]):
        return "support"
    elif any(word in text for word in ["احجز", "جلسة", "موعد", "حجز"]):
        return "booking"
    else:
        return "casual"

# ==============================
# كلاس ConversationController
# ==============================

class ConversationController:
    """
    يدير المحادثة بالكامل: الحالة، الذاكرة، توجيه الطلبات إلى LLM أو agent.
    """

    def __init__(self):
        self.messages: List[BaseMessage] = []
        self.state: str = "neutral"  # possible: neutral, support_mode, education_mode, booking_mode
        # إضافة رسالة النظام في بداية المحادثة
        self.messages.append(SystemMessage(content=SYSTEM_PROMPT))
        logger.info("ConversationController initialized with state: %s", self.state)

    def _update_state(self, intent: str):
        """تحديث الحالة بناءً على النية."""
        if intent == "education":
            self.state = "education_mode"
        elif intent == "support":
            self.state = "support_mode"
        elif intent == "booking":
            self.state = "booking_mode"
        else:  # casual
            self.state = "neutral"
        logger.info("State updated to: %s", self.state)

    def _call_llm_directly(self, messages: List[BaseMessage]) -> str:
        """استدعاء النموذج مباشرة بدون agent."""
        response = llm.invoke(messages)
        return response.content

    def chat(self, user_input: str) -> str:
        # إضافة رسالة المستخدم
        self.messages.append(HumanMessage(content=user_input))

        # تحديد النية
        intent = detect_intent(user_input)
        logger.info("Detected intent: %s", intent)

        # تحديث الحالة
        self._update_state(intent)

        # تحديد مسار المعالجة
        if intent in ["education", "casual"]:
            # استخدام LLM مباشرة
            ai_content = self._call_llm_directly(self.messages)
            logger.info("Using direct LLM for intent: %s", intent)
        else:  # support or booking
            # استخدام agent مع إضافة تعليمات الحالة مؤقتاً
            state_instruction = f"الحالة الحالية للمحادثة: {self.state}. استخدم الأدوات المناسبة فقط."
            temp_messages = self.messages + [SystemMessage(content=state_instruction)]
            result = agent_executor.invoke({"messages": temp_messages})
            ai_content = result["messages"][-1].content
            logger.info("Using agent for intent: %s with state: %s", intent, self.state)

        # إضافة رد الوكيل إلى السجل
        self.messages.append(AIMessage(content=ai_content))

        # تطبيق النافذة المنزلقة (آخر 12 رسالة مع بقاء رسالة النظام)
        if len(self.messages) > 13:  # system + 12 others
            self.messages = [self.messages[0]] + self.messages[-12:]
        else:
            self.messages = self.messages[:1] + self.messages[-12:]  # في حالة عدد أقل

        # تسجيل استخدام الأداة (تقديري)
        if "تمارين التنفس" in ai_content or "خذ نفساً" in ai_content:
            logger.info("Tool used: breathing_exercise")
        elif "تم حجز الجلسة" in ai_content or "booking" in ai_content:
            logger.info("Tool used: schedule_session")

        return ai_content