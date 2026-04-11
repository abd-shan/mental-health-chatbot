# Installation & Setup

## Prerequisites

Before running the project, make sure the following are installed:

* **Python 3.12 or higher**
* **uv** (recommended package manager) or **pip**
* **OpenRouter API Key** with access to DeepSeek model

---

## Clone the Repository

```bash
git clone https://github.com/abd-shan/mental-health-chatbot
cd mental-health-chatbot
```

---

## Create Virtual Environment

### Recommended: Using uv

```bash
uv venv
source .venv/bin/activate
uv sync
```

---

### Alternative: Using pip

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Configure Environment Variables

Create a `.env` file in the project root:

```env
OPENROUTER_API_KEY=your_actual_key_here
```

---

## Run the Application

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The application will be available at:

```text
http://127.0.0.1:8000
```

---

# Docker Support

A lightweight Docker setup is included for deployment and reproducibility.

---

## Dockerfile

Create a file named `Dockerfile` in the project root:

```dockerfile
# Lightweight Python image
FROM python:3.12-slim

# Python runtime settings
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better Docker cache usage
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## .dockerignore

Create a file named `.dockerignore`:

```plaintext
.venv
venv
__pycache__
.env
.git
.pytest_cache
*.pyc
```

This prevents unnecessary files from being copied into the container and keeps the build lightweight.

---

## Build Docker Image

```bash
docker build -t mental-health-ai .
```

---

## Run Docker Container

```bash
docker run -p 8000:8000 mental-health-ai
```

---

# Deployment Notes

The project is lightweight enough for deployment on:

* Railway
* Render
* DigitalOcean
* Docker-based VPS

---

# Recommended Production Next Step

For production environments, it is recommended to place the service behind:

* Nginx reverse proxy
* HTTPS termination
* persistent session storage

---

