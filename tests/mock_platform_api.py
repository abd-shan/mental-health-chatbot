"""Small local server used only for Docker host-gateway smoke tests."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlparse


DOCTORS = {
    "message": "Doctors retrieved",
    "isSuccess": True,
    "data": {
        "items": [
            {
                "id": 8,
                "name": "Dr. John Smith",
                "bio": "خبرة في دعم حالات القلق",
                "rating": 4.5,
                "reviewCount": 10,
                "specialists": [
                    {
                        "id": 1,
                        "name": "Clinical Psychology",
                        "nameAr": "علم النفس الإكلينيكي",
                        "description": "Assessment and support for anxiety.",
                        "descriptionAr": "التقييم والدعم للقلق.",
                    }
                ],
                "availabilities": [
                    {"id": 1, "day": "SUNDAY", "startTime": "09:00", "endTime": "17:00"}
                ],
                "sessionPrices": [{"currency": "USD", "price": 50}],
            }
        ],
        "total": 1,
        "page": 1,
        "limit": 20,
    },
}

COURSES = {
    "message": "Courses retrieved successfully",
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
                "_count": {"lessons": 2, "enrollments": 1},
            }
        ],
        "pagination": {"page": 1, "limit": 20, "total": 1, "pages": 1},
    },
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/doctors":
            self._send(DOCTORS)
        elif path == "/api/courses":
            self._send(COURSES)
        else:
            self.send_error(404)

    def _send(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 3100), Handler).serve_forever()
