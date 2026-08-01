import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def test_health_reports_openrouter_configuration(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "openrouter")
        self.assertIn("llm_configured", response.json())

    def test_readiness_is_unavailable_without_openrouter_key(self) -> None:
        response = self.client.get("/health/ready")

        expected_status = 200 if main.OPENROUTER_API_KEY else 503
        self.assertEqual(response.status_code, expected_status)

    def test_catalog_status_endpoint_is_available_to_backend(self) -> None:
        response = self.client.get("/api/v1/catalog/status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("configured", response.json())

    def test_crisis_message_uses_deterministic_safety_response(self) -> None:
        response = self.client.post(
            "/api/v1/chat",
            json={"message": "أفكر بالانتحار"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["conversation_id"])
        self.assertEqual(payload["status"]["risk_level"], "urgent")
        self.assertIn("997", payload["response"])

    def test_empty_message_is_rejected(self) -> None:
        response = self.client.post("/api/v1/chat", json={"message": "   "})

        self.assertEqual(response.status_code, 422)

    def test_service_token_is_enforced_when_configured(self) -> None:
        original_key = main.AI_SERVICE_API_KEY
        main.AI_SERVICE_API_KEY = "test-service-secret"
        try:
            unauthorized = self.client.post(
                "/api/v1/chat",
                json={"message": "أفكر بالانتحار"},
            )
            authorized = self.client.post(
                "/api/v1/chat",
                headers={"X-Service-Token": "test-service-secret"},
                json={"message": "أفكر بالانتحار"},
            )
        finally:
            main.AI_SERVICE_API_KEY = original_key

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_summary_endpoint_returns_covered_message_ids(self) -> None:
        fake_summary_llm = unittest.mock.Mock()
        fake_summary_llm.invoke.return_value = SimpleNamespace(
            content="الموضوع: ضغط الدراسة\nغير محسوم: تنظيم وقت المراجعة"
        )
        with patch("agent.summary_llm", fake_summary_llm):
            response = self.client.post(
                "/api/v1/conversations/conversation-1/summary",
                json={
                    "existing_summary": None,
                    "messages": [
                        {"id": "m1", "role": "user", "content": "أنا قلق من الاختبار"},
                        {"id": "m2", "role": "assistant", "content": "لنضع خطة بسيطة"},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["covered_message_ids"], ["m1", "m2"])
        self.assertIn("ضغط الدراسة", response.json()["summary"])

    def test_conversation_purge_is_idempotent(self) -> None:
        main.get_or_create_session("conversation-to-delete")
        self.assertIn("conversation-to-delete", main.sessions)

        first = self.client.delete("/api/v1/conversations/conversation-to-delete")
        second = self.client.delete("/api/v1/conversations/conversation-to-delete")

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 204)
        self.assertNotIn("conversation-to-delete", main.sessions)


if __name__ == "__main__":
    unittest.main()
