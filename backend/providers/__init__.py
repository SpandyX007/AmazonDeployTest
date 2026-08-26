"""Provider registry.

Importing this package registers every provider below. To add a vendor:
create a module here, decorate the class with `@register`, and import it in
the block at the bottom — nothing else in the app needs to change.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Pin to backend/.env so keys are found regardless of the working directory.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .base import (  # noqa: E402
    ChatMessage,
    ModelInfo,
    Provider,
    ProviderError,
    ProviderStatus,
    StreamItem,
    Usage,
    estimate_tokens,
    estimate_usage,
    register,
    registry,
)

# --- registered providers -------------------------------------------------
from . import gemini_provider  # noqa: E402,F401
from . import groq_provider  # noqa: E402,F401
from . import ollama_provider  # noqa: E402,F401

__all__ = [
    "ChatMessage",
    "ModelInfo",
    "Provider",
    "ProviderError",
    "ProviderStatus",
    "StreamItem",
    "Usage",
    "estimate_tokens",
    "estimate_usage",
    "register",
    "registry",
]


def get_provider(provider_id: str) -> Provider | None:
    return registry.get(provider_id)


def list_providers() -> list[Provider]:
    return registry.all()


def catalog() -> list[dict]:
    """Full provider + model catalog, as sent to the frontend."""
    return [provider.describe() for provider in registry.all()]
