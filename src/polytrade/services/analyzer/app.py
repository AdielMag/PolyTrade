from __future__ import annotations

from fastapi import FastAPI

from .analysis import run_analysis
from ...shared.logging import configure_logging

configure_logging()

app = FastAPI()


@app.post("/run")
def run() -> dict[str, int]:
    out = run_analysis()
    return {"created": len(out)}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}

