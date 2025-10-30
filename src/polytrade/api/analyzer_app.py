from __future__ import annotations

from fastapi import FastAPI

from ..analysis import run_analysis


app = FastAPI()


@app.post("/run")
def run():
    out = run_analysis()
    return {"created": len(out)}


@app.get("/health")
def health():
    return {"ok": True}


