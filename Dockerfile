FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --upgrade pip

COPY pyproject.toml poetry.lock* ./
COPY README.md ./
COPY src ./src

# Install project and dependencies using PEP 517 (poetry-core backend)
# This installs from the local sources we just copied
RUN pip install --no-cache-dir .

ENV PORT=8080
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT}"]