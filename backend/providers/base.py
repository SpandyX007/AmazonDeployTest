"""Core provider contract.

Every LLM backend (Groq, Gemini, Ollama, ...) implements `Provider`. The API
layer only ever talks to this interface, so adding a vendor never touches
routing code — see providers/README.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Iterable, Iterator, Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class ModelInfo:
    """One selectable model, plus the metadata the picker renders."""

    id: str
    name: str
    tagline: str = ""
    context: str = "—"
    speed: Literal["Fastest", "Fast", "Balanced", "Deep"] = "Balanced"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProviderStatus:
    available: bool
    #: Human-readable reason shown in the UI when unavailable.
    detail: str = ""


class ProviderError(RuntimeError):
    """Raised for provider misconfiguration or an upstream failure."""


class Provider(ABC):
    #: Stable slug used on the wire, e.g. "groq".
    id: str
    #: Display name in the picker.
    label: str
    #: Two-letter badge, e.g. "GQ".
    initials: str
    #: Hue (0-360) driving the provider's accent colour in the UI.
    hue: int
    #: Shown when the provider is unavailable, e.g. "Set GROQ_API_KEY".
    setup_hint: str = ""

    @abstractmethod
    def status(self) -> ProviderStatus:
        """Whether this provider is usable right now (key set, daemon up)."""

    @abstractmethod
    def models(self) -> list[ModelInfo]:
        """Selectable models. May be discovered at call time."""

    @abstractmethod
    def stream(self, model: str, messages: Iterable[ChatMessage]) -> Iterator[str]:
        """Yield response text chunks for the given conversation."""

    def complete(self, model: str, messages: Iterable[ChatMessage]) -> str:
        """Non-streaming convenience built on top of `stream`."""
        return "".join(self.stream(model, messages))

    def describe(self) -> dict:
        """Catalog entry consumed by the frontend."""
        status = self.status()
        try:
            models = [m.as_dict() for m in self.models()] if status.available else []
        except Exception as exc:  # discovery is best-effort; never break the catalog
            return {
                "id": self.id,
                "label": self.label,
                "initials": self.initials,
                "hue": self.hue,
                "available": False,
                "detail": f"Could not list models: {exc}",
                "setupHint": self.setup_hint,
                "models": [],
            }

        return {
            "id": self.id,
            "label": self.label,
            "initials": self.initials,
            "hue": self.hue,
            "available": status.available and bool(models),
            "detail": status.detail or ("" if models else "No models available"),
            "setupHint": self.setup_hint,
            "models": models,
        }


@dataclass
class _Registry:
    _providers: dict[str, Provider] = field(default_factory=dict)

    def register(self, provider: Provider) -> Provider:
        if provider.id in self._providers:
            raise ValueError(f"Provider id '{provider.id}' is already registered")
        self._providers[provider.id] = provider
        return provider

    def get(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def all(self) -> list[Provider]:
        return list(self._providers.values())


registry = _Registry()


def register(provider_cls: type[Provider]) -> type[Provider]:
    """Class decorator: instantiate and add a provider to the registry."""
    registry.register(provider_cls())
    return provider_cls
