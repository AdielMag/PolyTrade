from __future__ import annotations

from fastapi import FastAPI

from ..monitor import run_monitor


app = FastAPI()


@app.post("/run")
def run():
    return run_monitor()


@app.get("/health")
def health():
    return {"ok": True}


