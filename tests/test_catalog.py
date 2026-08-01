import unittest

from catalog import PlatformPublicCatalog


class PlatformPublicCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = []

        def fake_fetch(path, params):
            self.calls.append((path, params))
            if path == "/api/doctors":
                return {
                    "isSuccess": True,
                    "data": {
                        "items": [
                            {
                                "id": 8,
                                "name": "Dr. John Smith",
                                "image": "/private-to-prompt.jpg",
                                "bio": "خبرة في علاج القلق",
                                "rating": 4.5,
                                "reviewCount": 10,
                                "specialists": [
                                    {
                                        "id": 1,
                                        "name": "Clinical Psychology",
                                        "nameAr": "علم النفس الإكلينيكي",
                                        "description": "Anxiety support",
                                        "descriptionAr": "دعم القلق",
                                    }
                                ],
                                "availabilities": [
                                    {
                                        "day": "SUNDAY",
                                        "startTime": "09:00",
                                        "endTime": "17:00",
                                    }
                                ],
                                "sessionPrices": [{"currency": "USD", "price": 50}],
                            }
                        ],
                        "total": 1,
                    },
                }
            if path == "/api/courses":
                return {
                    "isSuccess": True,
                    "data": {
                        "courses": [
                            {
                                "id": 3,
                                "title": "إدارة القلق",
                                "isPublished": True,
                                "isActive": True,
                                "isFree": False,
                                "category": {"id": 1, "name": "Anxiety", "nameAr": "القلق"},
                                "doctor": {"id": 8, "name": "Dr. John Smith"},
                                "_count": {"lessons": 2},
                            },
                            {
                                "id": 99,
                                "title": "مسودة مخفية",
                                "isPublished": False,
                                "isActive": True,
                            },
                        ],
                        "pagination": {"pages": 1},
                    },
                }
            raise AssertionError(f"Unexpected path: {path}")

        self.catalog = PlatformPublicCatalog(
            "http://backend:3000",
            cache_ttl_seconds=300,
            fetch_json=fake_fetch,
        )

    def test_retrieves_relevant_doctors_and_courses(self) -> None:
        context = self.catalog.get_relevant_context("أحتاج طبيباً ودورة للقلق", "booking")

        self.assertIsNotNone(context)
        self.assertEqual(context["doctors"][0]["id"], 8)
        self.assertEqual(context["courses"][0]["id"], 3)
        self.assertNotIn("image", context["doctors"][0])
        self.assertEqual(
            context["sources"],
            ["public-api:/api/doctors", "public-api:/api/courses"],
        )

    def test_cache_avoids_refetch_within_ttl(self) -> None:
        self.catalog.get_relevant_context("القلق", "support")
        self.catalog.get_relevant_context("دورة القلق", "education")

        self.assertEqual(len(self.calls), 2)

    def test_status_reports_normalized_counts(self) -> None:
        self.catalog.refresh(force=True)
        status = self.catalog.status()

        self.assertEqual(status["doctor_count"], 1)
        self.assertEqual(status["course_count"], 1)
        self.assertIsNone(status["last_error"])


if __name__ == "__main__":
    unittest.main()
