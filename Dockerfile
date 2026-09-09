# syntax=docker/dockerfile:1
# ==========================================
# STAGE 1: BACKEND BUILD & VALIDATION RUNNER
# ==========================================
FROM python:3.11-slim AS backend-runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml workflow.py server.py ./
COPY tests/backend/ ./tests/backend/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastapi[all] \
    pydantic \
    langgraph \
    pytest \
    pytest-cov \
    httpx \
    ruff \
    mypy

RUN ruff check . && mypy --strict workflow.py server.py
RUN pytest --cov=. --cov-report=xml --cov-fail-under=90 tests/backend/

# ==========================================
# STAGE 2: FRONTEND E2E & ACCESSIBILITY RUNNER
# ==========================================
FROM mcr.microsoft.com/playwright:v1.40.0-jammy AS frontend-runner

WORKDIR /app

COPY package.json ./
RUN npm install

COPY app/ ./app/
COPY tests/e2e/ ./tests/e2e/

RUN npx playwright install --with-deps chromium

CMD ["npm", "run", "test:e2e"]
