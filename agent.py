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
# System Prompt
# ==============================

SYSTEM_PROMPT = """
أنت مساعد متخصص في الدعم النفسي تم تطويرك ضمن منصة "عون".

الهوية:
- التطبيق من تطوير فريق منصة عون.
- المطور التقني: المهندس عبدالقادر الشنبور.
- تقدم دعماً نفسياً متوافقاً مع القيم الإسلامية والأخلاق السليمة.

المبادئ:
- عزز الطمأنينة، الصبر، ضبط النفس، والعفة.
- لا تشجع أو تبرر أي سلوك محرم أو ضار مثل الإباحية، الزنا، الخمور، أو الإدمان.
- إذا طُلب أمر مخالف، وجّه بلطف نحو بديل صحي ونقي.
- لا تكن واعظاً قاسياً، بل موجهاً رحيماً.
- لا تقدم تشخيصات طبية.
- استخدم لغة هادئة متزنة.

آلية التفاعل:
- افهم السياق أولاً.
- اسأل أسئلة استكشافية.
- يمكن إدماج بعد روحي عند الحاجة بشكل طبيعي وغير مباشر.
"""

# ==============================
# Agent
# ==============================

agent_executor = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
)

# ==============================
# Content Filter
# ==============================

def contains_prohibited_content(text: str) -> bool:
    text = text.lower()
    prohibited_keywords = [
        "اباحية", "اباحي", "porn",
        "زنا", "علاقة محرمة",
        "خمور", "كحول", "سكر",
        "عادة سرية", "استمناء"
    ]
    return any(word in text for word in prohibited_keywords)

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
    else:
        return "casual"

# ==============================
# Conversation Controller
# ==============================

class ConversationController:

    def __init__(self):
        self.messages: List[BaseMessage] = []
        self.messages.append(SystemMessage(content=SYSTEM_PROMPT))
        self.state = "neutral"

    def _call_llm(self, messages: List[BaseMessage]) -> str:
        try:
            response = llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.exception("LLM call failed")
            return "حدث خطأ مؤقت في المعالجة، حاول مرة أخرى."

    def chat(self, user_input: str) -> str:

        # فلترة المحتوى المحرم
        if contains_prohibited_content(user_input):
            return (
                "أفهم أن هناك أموراً قد تشغل بالك، لكن من المهم أن نحافظ على نقاء النفس وسلامتها.\n\n"
                "إذا كنت تواجه صراعاً داخلياً، يمكننا الحديث عن طرق صحية ونقية "
                "للتعامل مع الضغوط والرغبات.\n\n"
                "ما الذي تشعر به تحديداً؟"
            )

        self.messages.append(HumanMessage(content=user_input))

        intent = detect_intent(user_input)

        if intent in ["education", "casual"]:
            ai_content = self._call_llm(self.messages)

        else:
            state_instruction = SystemMessage(
                content=f"الحالة الحالية: {intent}. استخدم الأدوات فقط إذا لزم الأمر."
            )
            temp_messages = self.messages + [state_instruction]
            try:
                result = agent_executor.invoke({"messages": temp_messages})
                ai_content = result["messages"][-1].content
            except Exception:
                logger.exception("Agent failed")
                ai_content = "حدث خطأ مؤقت، حاول مرة أخرى."

        self.messages.append(AIMessage(content=ai_content))

        # Sliding Window Memory
        system_msg = self.messages[0]
        history = self.messages[1:]
        history = history[-12:]
        self.messages = [system_msg] + history

        return ai_content
