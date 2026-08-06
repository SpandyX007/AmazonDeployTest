"""HTTP surface for the multi-provider chat service.

Routing is provider-agnostic: everything is resolved through the registry in
`backend.providers`, so a new vendor needs no changes here.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterator, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Loaded as a top-level module (`uvicorn main:app` from backend/) rather than as
# part of the package (`uvicorn backend.main:app` from the repo root) — put the
# repo root on the path so the import below resolves either way.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.providers import ChatMessage, catalog, get_provider, list_providers  # noqa: E402

app = FastAPI(title="LLM API Service")

_configured = os.getenv("ALLOWED_ORIGINS", "")
_origins = [o.strip() for o in _configured.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # With nothing configured, accept any localhost port so `npm run dev` just works.
    allow_origin_regex=None if _origins else r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- schemas ---------------------------------------------------------------


class Turn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    provider: str
    model: str
    messages: list[Turn] = Field(min_length=1)
    system: str | None = None

    def to_provider_messages(self) -> list[ChatMessage]:
        turns = [ChatMessage(role=t.role, content=t.content) for t in self.messages]
        if self.system:
            turns.insert(0, ChatMessage(role="system", content=self.system))
        return turns


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str


class Query(BaseModel):
    query: str


class Answer(BaseModel):
    response: str


# --- helpers ---------------------------------------------------------------


def _resolve(request: ChatRequest):
    provider = get_provider(request.provider)
    if provider is None:
        raise HTTPException(404, f"Unknown provider '{request.provider}'")

    status = provider.status()
    if not status.available:
        raise HTTPException(503, status.detail or f"{provider.label} is not available")

    if not request.model.strip():
        raise HTTPException(422, "A model id is required")

    return provider


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# --- routes ----------------------------------------------------------------


@app.get("/")
async def index():
    return {"status": "The service is live"}


@app.get("/api/providers")
async def providers():
    """Provider + model catalog, with a sensible default selection."""
    entries = catalog()
    default = next((p for p in entries if p["available"] and p["models"]), None)

    return {
        "providers": entries,
        "default": (
            {"provider": default["id"], "model": default["models"][0]["id"]} if default else None
        ),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    provider = _resolve(request)
    try:
        content = provider.complete(request.model, request.to_provider_messages())
    except Exception as exc:
        raise HTTPException(502, f"{provider.label} request failed: {exc}")

    return ChatResponse(provider=provider.id, model=request.model, content=content)


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    provider = _resolve(request)
    messages = request.to_provider_messages()

    def events() -> Iterator[str]:
        try:
            for chunk in provider.stream(request.model, messages):
                yield _sse("token", {"text": chunk})
        except Exception as exc:
            yield _sse("error", {"message": f"{provider.label} request failed: {exc}"})
        yield _sse("done", {"provider": provider.id, "model": request.model})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/response", response_model=Answer)
def get_response(payload: Query):
    """Legacy single-shot endpoint — uses the first available provider."""
    provider = next((p for p in list_providers() if p.status().available), None)
    if provider is None:
        raise HTTPException(503, "No LLM provider is configured")

    models = provider.models()
    if not models:
        raise HTTPException(503, f"{provider.label} has no models available")

    try:
        answer = provider.complete(models[0].id, [ChatMessage(role="user", content=payload.query)])
    except Exception as exc:
        raise HTTPException(502, f"LLM request failed: {exc}")

    return Answer(response=answer)
