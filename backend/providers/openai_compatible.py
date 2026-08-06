"""Shared base for any vendor speaking the OpenAI chat-completions wire format.

Groq, Gemini, OpenRouter, Together, vLLM and friends all expose one, so a new
provider usually only needs a base URL, an env var and a model catalog.
"""

from __future__ import annotations

import os
from typing import Iterable, Iterator

from openai import OpenAI

from .base import ChatMessage, ModelInfo, Provider, ProviderError, ProviderStatus


class OpenAICompatibleProvider(Provider):
    #: Environment variable holding the API key.
    api_key_env: str
    #: OpenAI-compatible endpoint root.
    base_url: str
    #: Hand-curated model list shown in the picker.
    catalog: list[ModelInfo] = []

    def __init__(self) -> None:
        self._client: OpenAI | None = None

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env) or None

    def status(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(False, f"{self.api_key_env} is not set")
        return ProviderStatus(True)

    def models(self) -> list[ModelInfo]:
        return list(self.catalog)

    def client(self) -> OpenAI:
        # Built lazily so a missing key disables one provider instead of
        # crashing the whole service at import time.
        if self._client is None:
            key = self.api_key
            if not key:
                raise ProviderError(f"{self.api_key_env} is not set in the environment")
            self._client = OpenAI(api_key=key, base_url=self.base_url)
        return self._client

    def stream(self, model: str, messages: Iterable[ChatMessage]) -> Iterator[str]:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        try:
            response = self.client().chat.completions.create(
                model=model,
                messages=payload,
                stream=True,
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text
