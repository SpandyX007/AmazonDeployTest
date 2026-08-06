"""Ollama — models running locally. The catalog is whatever you've pulled."""

from __future__ import annotations

import os
import time
from typing import Any, Iterable, Iterator

from .base import ChatMessage, ModelInfo, Provider, ProviderError, ProviderStatus, register

#: Discovery hits the local daemon, so cache it briefly rather than per request.
_CACHE_TTL_SECONDS = 5.0


class _ThinkUnsupported(Exception):
    """The daemon or client rejected the `think` flag — retry without it."""


def _rejects_think(exc: Exception) -> bool:
    """True for "model does not support thinking" and old-client TypeErrors."""
    return "think" in str(exc).lower()


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a pydantic model or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _speed_for(parameter_size: str | None) -> str:
    """Rough tier from the parameter count, e.g. "7.6B" -> "Fast"."""
    if not parameter_size:
        return "Balanced"
    try:
        billions = float(str(parameter_size).upper().rstrip("B"))
    except ValueError:
        return "Balanced"
    if billions <= 4:
        return "Fastest"
    if billions <= 15:
        return "Fast"
    if billions <= 40:
        return "Balanced"
    return "Deep"


@register
class OllamaProvider(Provider):
    id = "ollama"
    label = "Ollama"
    initials = "OL"
    hue = 266
    setup_hint = "Start the Ollama app, then `ollama pull llama3.2`"

    def __init__(self) -> None:
        self._client: Any = None
        self._cache: tuple[float, list[ModelInfo]] | None = None
        self._error: str = ""
        #: Models whose server rejected `think` — stop sending it to them.
        self._no_think: set[str] = set()

    @property
    def host(self) -> str:
        return os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    def client(self) -> Any:
        if self._client is None:
            try:
                import ollama
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise ProviderError("The `ollama` package is not installed") from exc
            self._client = ollama.Client(host=self.host, timeout=300)
        return self._client

    def _discover(self) -> list[ModelInfo]:
        cached = self._cache
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        try:
            listing = self.client().list()
        except Exception as exc:
            self._error = f"Ollama is not reachable at {self.host}"
            self._cache = (time.monotonic(), [])
            raise ProviderError(f"{self._error}: {exc}") from exc

        models: list[ModelInfo] = []
        for entry in _attr(listing, "models", []) or []:
            name = _attr(entry, "model") or _attr(entry, "name")
            if not name:
                continue
            details = _attr(entry, "details")
            parameter_size = _attr(details, "parameter_size") if details else None
            quantization = _attr(details, "quantization_level") if details else None
            facts = [f for f in ("Local", parameter_size, quantization) if f]
            models.append(
                ModelInfo(
                    id=str(name),
                    name=str(name).split(":")[0].split("/")[-1],
                    tagline=" · ".join(str(f) for f in facts),
                    context="local",
                    speed=_speed_for(parameter_size),
                )
            )

        models.sort(key=lambda m: m.id)
        self._error = "" if models else "No models pulled yet"
        self._cache = (time.monotonic(), models)
        return models

    def status(self) -> ProviderStatus:
        try:
            models = self._discover()
        except ProviderError as exc:
            return ProviderStatus(False, str(exc).split(":")[0])
        if not models:
            return ProviderStatus(False, "No models pulled yet")
        return ProviderStatus(True)

    def models(self) -> list[ModelInfo]:
        try:
            return self._discover()
        except ProviderError:
            return []

    def stream(self, model: str, messages: Iterable[ChatMessage]) -> Iterator[str]:
        payload = [{"role": m.role, "content": m.content} for m in messages]

        # Reasoning models are far slower with thinking on — roughly 20s versus
        # 1s for a 4B qwen3.5 — and this endpoint discards the thinking text
        # anyway, so it buys nothing. Older daemons reject the flag; those
        # models fall back once and are remembered.
        try:
            yield from self._emit(model, payload, suppress_thinking=model not in self._no_think)
        except _ThinkUnsupported:
            self._no_think.add(model)
            yield from self._emit(model, payload, suppress_thinking=False)

    def _emit(self, model: str, payload: list[dict], suppress_thinking: bool) -> Iterator[str]:
        options = {"think": False} if suppress_thinking else {}
        emitted = False
        try:
            # With stream=True the client is lazy: the request is issued on the
            # first iteration, so errors surface here rather than at the call.
            for chunk in self.client().chat(model=model, messages=payload, stream=True, **options):
                message = _attr(chunk, "message")
                text = _attr(message, "content") if message else None
                if text:
                    emitted = True
                    yield text
        except Exception as exc:
            # Only safe to retry while nothing has reached the client yet.
            if suppress_thinking and not emitted and _rejects_think(exc):
                raise _ThinkUnsupported from exc
            raise ProviderError(str(exc)) from exc
