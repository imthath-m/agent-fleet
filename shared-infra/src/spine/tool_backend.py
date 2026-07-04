"""Local tool backend (Cloud Run target in production).

A small FastAPI app exposing a "hello" tool. Deployed statelessly per the
plan's Cloud Run "tool backend" role.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="spine-tool-backend", version="0.1.0")


class HelloResponse(BaseModel):
    message: str


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools/hello", response_model=HelloResponse)
def hello(name: str = "world") -> HelloResponse:
    """Return a greeting. The canonical Phase 1 'hello' tool."""
    return HelloResponse(message=f"hello, {name}")
