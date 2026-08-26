"""Google Gemini, via its OpenAI-compatible endpoint.

Using the compatibility layer keeps the dependency list to the openai SDK
we already ship.
"""

from __future__ import annotations

import os

from .base import ModelInfo, ProviderStatus, register
from .openai_compatible import OpenAICompatibleProvider


@register
class GeminiProvider(OpenAICompatibleProvider):
    id = "gemini"
    label = "Gemini"
    initials = "GM"
    hue = 214
    setup_hint = "Add GEMINI_API_KEY to backend/.env"

    api_key_env = "GEMINI_API_KEY"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # The gemini-2.x ids were retired for new users (404 "no longer available
    # to new users"); these are the replacements Google's error messages point
    # to. Verify against GET /v1beta/models if one of them 404s again.
    catalog = [
        ModelInfo(
            id="gemini-3.6-flash",
            name="Gemini 3.6 Flash",
            tagline="Fast, capable default for most conversations",
            context="1M",
            speed="Fastest",
        ),
        ModelInfo(
            id="gemini-3.1-pro-preview",
            name="Gemini 3.1 Pro",
            tagline="Deepest reasoning across long documents and code",
            context="1M",
            speed="Deep",
        ),
        ModelInfo(
            id="gemini-3.5-flash-lite",
            name="Gemini 3.5 Flash Lite",
            tagline="Cheapest tier — classification and quick lookups",
            context="1M",
            speed="Fastest",
        ),
        ModelInfo(
            id="gemini-3.5-flash",
            name="Gemini 3.5 Flash",
            tagline="Previous generation workhorse",
            context="1M",
            speed="Fast",
        ),
    ]

    @property
    def api_key(self) -> str | None:
        # GOOGLE_API_KEY is the name the Google SDKs use; accept either.
        return os.getenv(self.api_key_env) or os.getenv("GOOGLE_API_KEY") or None

    def status(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(False, "GEMINI_API_KEY is not set")
        return ProviderStatus(True)
