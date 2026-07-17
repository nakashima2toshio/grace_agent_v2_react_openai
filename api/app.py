"""FastAPI application for GRACE Support."""

from __future__ import annotations

import os
import socket

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.agent_support import router

app = FastAPI(title="GRACE Support API", version="1.0.0")

origins = [item.strip() for item in os.getenv(
    "AGENT_SUPPORT_CORS_ORIGINS", "http://localhost:5173"
).split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, object]:
    qdrant_ok = _port_open(os.getenv("QDRANT_HOST", "localhost"), 6333)
    redis_ok = _port_open(os.getenv("REDIS_HOST", "localhost"), 6379)
    return {
        "ready": bool(os.getenv("OPENAI_API_KEY")) and qdrant_ok,
        "services": {
            "openai": "configured" if os.getenv("OPENAI_API_KEY") else "missing",
            "qdrant": "available" if qdrant_ok else "unavailable",
            "redis": "available" if redis_ok else "unavailable",
        },
    }


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False
