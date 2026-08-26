"""Shared base for any vendor speaking the OpenAI chat-completions wire format.

Groq, Gemini, OpenRouter, Together, vLLM and friends all expose one, so a new
provider usually only needs a base URL, an env var and a model catalog.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Iterator

from openai import OpenAI

from .base import (
    ChatMessage,
    ModelInfo,
    Provider,
    ProviderError,
    ProviderStatus,
    StreamItem,
    Usage,
)


def _usage_from(chunk: Any) -> Usage | None:
    """Pull a usage block off a streamed chunk, wherever the vendor put it.

    OpenAI proper (and Gemini's shim) attach `usage` to a final chunk when
    `stream_options.include_usage` is on. Groq also tucks a copy under a
    vendor extension, `x_groq.usage`, which the SDK keeps in `model_extra`.
    """
    usage = getattr(chunk, "usage", None)
    if usage is None:
        extra = getattr(chunk, "model_extra", None) or {}
        vendor = extra.get("x_groq") if isinstance(extra, dict) else None
        if isinstance(vendor, dict):
            usage = vendor.get("usage")

    if usage is None:
        return None

    read = usage.get if isinstance(usage, dict) else lambda k, d=None: getattr(usage, k, d)
    prompt = read("prompt_tokens")
    completion = read("completion_tokens")
    if prompt is None and completion is None:
        return None
    return Usage(prompt_tokens=int(prompt or 0), completion_tokens=int(completion or 0))


class OpenAICompatibleProvider(Provider):
    #: Environment variable holding the API key.
    api_key_env: str
    #: OpenAI-compatible endpoint root.
    base_url: str
    #: Hand-curated model list shown in the picker.
    catalog: list[ModelInfo] = []

    def __init__(self) -> None:
        self._client: OpenAI | None = None
        #: Set once a vendor rejects `stream_options` — not every shim knows
        #: the parameter, and the fallback is an estimate, not a failure.
        self._no_stream_options = False

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

    def _open(self, model: str, payload: list[dict], max_output_tokens: int | None):
        params: dict[str, Any] = {"model": model, "messages": payload, "stream": True}
        if max_output_tokens:
            params["max_tokens"] = max_output_tokens
        if not self._no_stream_options:
            params["stream_options"] = {"include_usage": True}

        try:
            return self.client().chat.completions.create(**params)
        except Exception as exc:
            # An unknown-parameter rejection is the one error worth retrying:
            # drop the option, remember that, and carry on without usage.
            if "stream_options" in params and "stream_options" in str(exc):
                self._no_stream_options = True
                params.pop("stream_options")
                try:
                    return self.client().chat.completions.create(**params)
                except Exception as retry_exc:
                    raise ProviderError(str(retry_exc)) from retry_exc
            raise ProviderError(str(exc)) from exc

    def stream(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        *,
        max_output_tokens: int | None = None,
    ) -> Iterator[StreamItem]:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        response = self._open(model, payload, max_output_tokens)

        usage: Usage | None = None
        for chunk in response:
            # The usage-bearing chunk has no choices; keep the newest one seen,
            # since some vendors send running totals on every chunk.
            found = _usage_from(chunk)
            if found is not None:
                usage = found
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text

        if usage is not None:
            yield usage
