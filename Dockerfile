# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system --gid 10001 aoun \
    && adduser --system --uid 10001 --ingroup aoun --home /nonexistent aoun

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY agent.py catalog.py main.py prompting.py summarization.py ./
COPY templates ./templates
COPY static ./static

USER 10001:10001

# EXPOSE documents the container port; it does not publish it on the host.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--no-server-header"]
