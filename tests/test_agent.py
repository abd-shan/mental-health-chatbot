from types import SimpleNamespace
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage, SystemMessage

from agent import ConversationController


class CapturingLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages)
        return SimpleNamespace(content=self.content)


class ConversationControllerTests(unittest.TestCase):
    def test_structured_pre_query_is_sent_before_user_message(self) -> None:
        fake_llm = CapturingLlm("يمكنني مساعدتك في معرفة خيارات الحجز المتاحة.")
        controller = ConversationController()

        with patch("agent.llm", fake_llm):
            result = controller.chat(
                "أريد حجز موعد مع أخصائي",
                patient_profile={"name": "مستخدم تجريبي"},
            )

        prompt = fake_llm.prompts[0]
        self.assertIsInstance(prompt[0], SystemMessage)
        self.assertIn('<turn_plan source="server">', prompt[0].content)
        self.assertIn("intent: booking", prompt[0].content)
        self.assertIsInstance(prompt[-1], HumanMessage)
        self.assertEqual(prompt[-1].content, "أريد حجز موعد مع أخصائي")
        self.assertEqual(result["status"]["response_mode"], "booking_preparation")

    def test_output_guard_rejects_unverified_booking_claim(self) -> None:
        fake_llm = CapturingLlm("تم حجز موعدك بنجاح وموعدك مؤكد.")
        controller = ConversationController()

        with patch("agent.llm", fake_llm):
            result = controller.chat("أريد حجز موعد")

        self.assertNotIn("تم حجز", result["response"])
        self.assertIn("لا يمكنني تأكيد موعد", result["response"])

    def test_backend_summary_and_recent_messages_are_used_as_context(self) -> None:
        fake_llm = CapturingLlm("أتذكر السياق، ما أكثر شيء يسبب لك القلق الآن؟")
        controller = ConversationController()

        with patch("agent.llm", fake_llm):
            controller.chat(
                "ما زلت أشعر بالقلق",
                conversation_summary="المستخدم تحدث سابقاً عن ضغط الدراسة.",
                recent_messages=[
                    {"id": "m1", "role": "user", "content": "لدي اختبار قريب"},
                    {"id": "m2", "role": "assistant", "content": "كيف تستعد للاختبار؟"},
                ],
            )

        prompt = fake_llm.prompts[0]
        self.assertIn("<conversation_memory", prompt[0].content)
        self.assertIn("ضغط الدراسة", prompt[0].content)
        self.assertEqual(prompt[1].content, "لدي اختبار قريب")
        self.assertEqual(prompt[2].content, "كيف تستعد للاختبار؟")
        self.assertEqual(prompt[3].content, "ما زلت أشعر بالقلق")


if __name__ == "__main__":
    unittest.main()
