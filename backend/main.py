"""HTTP surface for the multi-provider chat service.

This module is just wiring: middleware, startup, and the two public routes.
The substance lives in the routers —

    backend/auth.py           signup, login, logout, `current_user`
    backend/conversations.py  thread CRUD (the sidebar)
    backend/chat.py           one assistant turn, against stored memory

Routing stays provider-agnostic: models are resolved through the registry in
`backend.providers`, so a new vendor needs no changes here.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Loaded as a top-level module (`uvicorn main:app` from backend/) rather than as
# part of the package (`uvicorn backend.main:app` from the repo root) — put the
# repo root on the path so the imports below resolve either way.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth import router as auth_router  # noqa: E402
from backend.chat import router as chat_router  # noqa: E402
from backend.conversations import router as conversations_router  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.providers import catalog  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LLM API Service", lifespan=lifespan)

_configured = os.getenv("ALLOWED_ORIGINS", "")
_origins = [o.strip() for o in _configured.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # With nothing configured, accept any localhost port so `npm run dev` just works.
    allow_origin_regex=None if _origins else r"http://(localhost|127\.0\.0\.1):\d+",
    # Required for the session cookie to travel at all. Note this rules out
    # `allow_origins=["*"]` — browsers refuse credentials against a wildcard,
    # which is why the origin list above must be explicit in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(chat_router)


@app.get("/")
async def index():
    return {"status": "The service is live"}


@app.get("/api/providers")
async def providers():
    """Provider + model catalog, with a sensible default selection.

    Left unauthenticated on purpose: the landing page uses it to show how many
    models are online, and it exposes no user data.
    """
    entries = catalog()
    default = next((p for p in entries if p["available"] and p["models"]), None)

    return {
        "providers": entries,
        "default": (
            {"provider": default["id"], "model": default["models"][0]["id"]} if default else None
        ),
    }
