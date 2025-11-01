from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from loguru import logger

from .monitor import run_monitor
from ...shared.logging import configure_logging

configure_logging()

app = FastAPI()


@app.post("/run")
def run() -> dict[str, Any]:
    logger.info("Received POST /run request - starting monitor")
    result = run_monitor()
    logger.info(f"Monitor complete - processed: {result['processed']}, closed: {result['closed']}, errors: {result['errors']}")
    return result


@app.get("/health")
def health() -> dict[str, bool]:
    logger.debug("Health check requested")
    return {"ok": True}

