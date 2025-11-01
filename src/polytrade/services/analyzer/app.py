from __future__ import annotations

from fastapi import FastAPI
from loguru import logger

from .analysis import run_analysis
from ...shared.logging import configure_logging

configure_logging()

app = FastAPI()


@app.post("/run")
def run() -> dict[str, int]:
    logger.info("Received POST /run request - starting analysis")
    out = run_analysis()
    logger.info(f"Analysis complete - returning {len(out)} suggestions")
    return {"created": len(out)}


@app.get("/health")
def health() -> dict[str, bool]:
    logger.debug("Health check requested")
    return {"ok": True}

