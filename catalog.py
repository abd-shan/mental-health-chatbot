"""Cached access to the main backend's public doctors and courses APIs."""

from collections.abc import Callable
import logging
import os
import threading
import time
from typing import Any, Optional

import httpx

from prompting import normalize_text


logger = logging.getLogger(__name__)

STOP_WORDS = {
    "انا",
    "اريد",
    "هل",
    "في",
    "من",
    "عن",
    "على",
    "الي",
    "الى",
    "مع",
    "هذا",
    "هذه",
    "ما",
    "هو",
    "هي",
    "او",
    "و",
}


class PlatformPublicCatalog:
    def __init__(
        self,
        base_url: Optional[str],
        *,
        cache_ttl_seconds: int = 300,
        request_timeout_seconds: float = 10,
        max_items: int = 100,
        fetch_json: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.cache_ttl_seconds = cache_ttl_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.max_items = max_items
        self._fetch_json = fetch_json
        self._lock = threading.Lock()
        self._doctors: list[dict[str, Any]] = []
        self._courses: list[dict[str, Any]] = []
        self._expires_at = 0.0
        self._last_success_at: Optional[float] = None
        self._last_error: Optional[str] = None

    @classmethod
    def from_environment(cls) -> "PlatformPublicCatalog":
        return cls(
            os.getenv("PLATFORM_API_BASE_URL"),
            cache_ttl_seconds=int(os.getenv("PLATFORM_CATALOG_CACHE_TTL_SECONDS", "300")),
            request_timeout_seconds=float(
                os.getenv("PLATFORM_API_TIMEOUT_SECONDS", "10")
            ),
            max_items=int(os.getenv("PLATFORM_CATALOG_MAX_ITEMS", "100")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url or self._fetch_json)

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._fetch_json:
            return self._fetch_json(path, params)
        if not self.base_url:
            raise RuntimeError("PLATFORM_API_BASE_URL is not configured")

        response = httpx.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("isSuccess") is not True:
            raise RuntimeError(f"Invalid public API envelope from {path}")
        return payload

    def _fetch_doctors(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page = 1
        page_limit = min(self.max_items, 100)
        while len(result) < self.max_items:
            payload = self._request(
                "/api/doctors",
                {"page": page, "limit": page_limit},
            )
            data = payload.get("data") or {}
            items = data.get("items") or []
            if not isinstance(items, list):
                raise RuntimeError("Doctors API returned invalid items")
            result.extend(item for item in items if isinstance(item, dict))
            total = data.get("total")
            if not items or not isinstance(total, int) or len(result) >= total:
                break
            page += 1
        return [self._normalize_doctor(item) for item in result[: self.max_items]]

    def _fetch_courses(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page = 1
        page_limit = min(self.max_items, 100)
        while len(result) < self.max_items:
            payload = self._request(
                "/api/courses",
                {"page": page, "limit": page_limit},
            )
            data = payload.get("data") or {}
            items = data.get("courses") or []
            if not isinstance(items, list):
                raise RuntimeError("Courses API returned invalid courses")
            result.extend(item for item in items if isinstance(item, dict))
            pagination = data.get("pagination") or {}
            pages = pagination.get("pages")
            if not items or not isinstance(pages, int) or page >= pages:
                break
            page += 1
        normalized = [self._normalize_course(item) for item in result[: self.max_items]]
        return [item for item in normalized if item["isPublished"] and item["isActive"]]

    @staticmethod
    def _normalize_doctor(item: dict[str, Any]) -> dict[str, Any]:
        specialists = []
        for specialist in item.get("specialists") or []:
            if not isinstance(specialist, dict):
                continue
            specialists.append(
                {
                    "id": specialist.get("id"),
                    "name": specialist.get("name"),
                    "nameAr": specialist.get("nameAr"),
                    "description": specialist.get("description"),
                    "descriptionAr": specialist.get("descriptionAr"),
                }
            )

        availabilities = []
        for availability in item.get("availabilities") or []:
            if not isinstance(availability, dict):
                continue
            availabilities.append(
                {
                    "day": availability.get("day"),
                    "startTime": availability.get("startTime"),
                    "endTime": availability.get("endTime"),
                }
            )

        prices = []
        for price in item.get("sessionPrices") or []:
            if not isinstance(price, dict):
                continue
            prices.append(
                {
                    "currency": price.get("currency"),
                    "price": price.get("price"),
                }
            )

        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "bio": item.get("bio"),
            "rating": item.get("rating"),
            "reviewCount": item.get("reviewCount"),
            "specialists": specialists,
            "availabilities": availabilities,
            "sessionPrices": prices,
            "updatedAt": item.get("updatedAt"),
        }

    @staticmethod
    def _normalize_course(item: dict[str, Any]) -> dict[str, Any]:
        category = item.get("category") or {}
        doctor = item.get("doctor") or {}
        counts = item.get("_count") or {}
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "isPublished": item.get("isPublished") is True,
            "isActive": item.get("isActive") is True,
            "isFree": item.get("isFree") is True,
            "category": {
                "id": category.get("id"),
                "name": category.get("name"),
                "nameAr": category.get("nameAr"),
            },
            "doctor": {
                "id": doctor.get("id"),
                "name": doctor.get("name"),
            },
            "lessonCount": counts.get("lessons"),
            "updatedAt": item.get("updatedAt"),
        }

    def refresh(self, *, force: bool = False) -> bool:
        if not self.configured:
            return False

        with self._lock:
            if not force and time.monotonic() < self._expires_at:
                return True

            try:
                doctors = self._fetch_doctors()
                courses = self._fetch_courses()
                self._doctors = doctors
                self._courses = courses
                self._last_success_at = time.time()
                self._last_error = None
                self._expires_at = time.monotonic() + self.cache_ttl_seconds
                logger.info(
                    "Platform catalog refreshed: %s doctors, %s courses",
                    len(doctors),
                    len(courses),
                )
                return True
            except Exception as exc:
                self._last_error = str(exc)
                self._expires_at = time.monotonic() + min(self.cache_ttl_seconds, 30)
                logger.warning("Platform catalog refresh failed: %s", exc)
                return bool(self._doctors or self._courses)

    @staticmethod
    def _query_terms(query: str) -> set[str]:
        terms: set[str] = set()
        for raw_term in normalize_text(query).split():
            if len(raw_term) <= 1 or raw_term in STOP_WORDS:
                continue
            variants = {raw_term}
            if raw_term.startswith("لل") and len(raw_term) > 4:
                variants.add(raw_term[2:])
            if raw_term[0] in "وفبكل" and len(raw_term) > 3:
                variants.add(raw_term[1:])
            for variant in list(variants):
                if variant.startswith("ال") and len(variant) > 4:
                    variants.add(variant[2:])
                if variant.endswith("ا") and len(variant) > 3:
                    variants.add(variant[:-1])
            terms.update(variant for variant in variants if len(variant) > 1)
        return terms

    @classmethod
    def _score(cls, query_terms: set[str], value: Any) -> int:
        searchable = normalize_text(str(value or ""))
        return sum(1 for term in query_terms if term in searchable)

    def get_relevant_context(
        self,
        query: str,
        intent: str,
        *,
        limit: int = 5,
    ) -> Optional[dict[str, Any]]:
        if not self.configured:
            return None
        self.refresh()
        with self._lock:
            doctors = list(self._doctors)
            courses = list(self._courses)

        terms = self._query_terms(query)
        scored_doctors = [
            (self._score(terms, doctor), doctor)
            for doctor in doctors
        ]
        scored_courses = [
            (self._score(terms, course), course)
            for course in courses
        ]

        relevant_doctors = [
            doctor
            for score, doctor in sorted(
                scored_doctors,
                key=lambda row: (row[0], bool(row[1].get("availabilities"))),
                reverse=True,
            )
            if score > 0
        ][:limit]
        relevant_courses = [
            course
            for score, course in sorted(scored_courses, key=lambda row: row[0], reverse=True)
            if score > 0
        ][:limit]

        if intent == "booking" and not relevant_doctors:
            relevant_doctors = sorted(
                doctors,
                key=lambda doctor: bool(doctor.get("availabilities")),
                reverse=True,
            )[:limit]

        course_requested = any(
            token in normalize_text(query)
            for token in ("دوره", "كورس", "تعلم", "محتوي", "course")
        )
        if course_requested and not relevant_courses:
            relevant_courses = courses[:limit]

        if not relevant_doctors and not relevant_courses:
            return None

        sources = []
        if relevant_doctors:
            sources.append("public-api:/api/doctors")
        if relevant_courses:
            sources.append("public-api:/api/courses")
        return {
            "sources": sources,
            "doctors": relevant_doctors,
            "courses": relevant_courses,
            "catalog_note": (
                "Availability entries are recurring public schedules, not confirmed bookable slots. "
                "Never claim a booking or exact slot without a booking tool result."
            ),
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "configured": self.configured,
                "base_url": self.base_url,
                "doctor_count": len(self._doctors),
                "course_count": len(self._courses),
                "last_success_at": self._last_success_at,
                "last_error": self._last_error,
                "cache_valid": time.monotonic() < self._expires_at,
            }


platform_catalog = PlatformPublicCatalog.from_environment()
