"""Core provider contract.

Every LLM backend (Groq, Gemini, Ollama, ...) implements `Provider`. The API
layer only ever talks to this interface, so adding a vendor never touches
routing code — see providers/README.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Iterable, Iterator, Literal, Union

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class Usage:
    """What one turn cost upstream, in the provider's own tokens.

    Yielded *last* by `Provider.stream`, after the text. It is the one thing
    the billing layer cannot reconstruct afterwards: by the time a stream ends
    the vendor has already metered it, and their count — not ours — is what
    they will invoice.

    `estimated` marks a count we made up from character lengths because the
    vendor sent nothing. Those rows are charged like any other but are flagged
    so they can be found (and, if the estimate was unfair, refunded).
    """

    prompt_tokens: int
    completion_tokens: int
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


#: What `Provider.stream` yields: text deltas, then at most one `Usage`.
StreamItem = Union[str, Usage]


def estimate_tokens(text: str) -> int:
    """Rough token count when the vendor gives none: ~4 characters per token.

    Deliberately not tiktoken — that would add a dependency that downloads
    its vocabulary at first use, and no local tokenizer matches every vendor
    anyway. This over-counts CJK and under-counts code slightly; the row is
    flagged `estimated` either way.
    """
    return max(1, (len(text) + 3) // 4)


def estimate_usage(messages: Iterable[ChatMessage], completion: str) -> Usage:
    """Fallback `Usage` from the payload we sent and the text we got back."""
    # Each message carries a few tokens of role/delimiter framing upstream.
    prompt = sum(estimate_tokens(m.content) + 4 for m in messages)
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=estimate_tokens(completion) if completion else 0,
        estimated=True,
    )


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
    def stream(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        *,
        max_output_tokens: int | None = None,
    ) -> Iterator[StreamItem]:
        """Yield response text chunks, then (if the vendor reports it) one `Usage`.

        `max_output_tokens` caps the completion. Billing relies on it: the
        cost of a turn is unknown until it ends, so this is what bounds how
        far past zero a nearly-empty balance can be driven by a single reply.
        """

    def complete(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        *,
        max_output_tokens: int | None = None,
    ) -> tuple[str, Usage | None]:
        """Non-streaming convenience built on top of `stream`."""
        parts: list[str] = []
        usage: Usage | None = None
        for item in self.stream(model, messages, max_output_tokens=max_output_tokens):
            if isinstance(item, Usage):
                usage = item
            else:
                parts.append(item)
        return "".join(parts), usage

    def find_model(self, model_id: str) -> ModelInfo | None:
        """The catalog entry for an id, or None if this provider has no such model."""
        try:
            return next((m for m in self.models() if m.id == model_id), None)
        except Exception:  # discovery failed — treat as unknown, not as a crash
            return None

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
