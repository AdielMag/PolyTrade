FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --upgrade pip

COPY pyproject.toml poetry.lock* ./

# Install project and dependencies using PEP 517 (poetry-core backend)
# This avoids requiring Poetry inside the image
RUN pip install --no-cache-dir .

COPY src ./src
COPY README.md ./

ENV PORT=8080
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT}"]