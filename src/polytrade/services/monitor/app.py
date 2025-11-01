from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .monitor import run_monitor
from ...shared.logging import configure_logging

configure_logging()

app = FastAPI()


@app.post("/run")
def run() -> dict[str, Any]:
    return run_monitor()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}

