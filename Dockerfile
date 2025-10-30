FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --upgrade pip

COPY pyproject.toml ./
RUN pip install poetry && poetry config virtualenvs.create false

COPY src ./src
COPY README.md ./

RUN poetry install --without dev --no-interaction --no-ansi

ENV PORT=8080
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT}"]


