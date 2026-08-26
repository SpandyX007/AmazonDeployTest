"""Which models are premium, and what each one charges per token.

The provider catalogs describe what *exists*; this module decides what is
*sellable* and at what price. It is configuration, not a table, on purpose —
until there is an admin panel to edit such rows, an env var the owner can
change without a deploy is the honest version of "controllable by me".

    policy_for("groq", <ModelInfo llama-3.1-8b-instant>)  -> free,    1 credit/token
    policy_for("groq", <ModelInfo gpt-oss-120b>)          -> premium, 5 credits/token
    policy_for("ollama", <ModelInfo llama3:70b>)          -> premium  (discovered size)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from backend.config import (
    FREE_CREDITS_PER_TOKEN,
    FREE_MODELS,
    PREMIUM_CREDITS_PER_TOKEN,
    PREMIUM_MODELS,
    PREMIUM_SPEEDS,
)
from backend.providers.base import ModelInfo, Usage

Tier = Literal["free", "premium"]


@dataclass(frozen=True)
class ModelPolicy:
    tier: Tier
    #: Credits charged per prompt token and per completion token.
    input_rate: float
    output_rate: float

    @property
    def premium(self) -> bool:
        return self.tier == "premium"

    def cost(self, usage: Usage) -> int:
        """Credits for one turn — rounded *up*, and never zero.

        A one-word reply still consumed a request; charging nothing for it
        would make "send a thousand tiny messages" free.
        """
        raw = usage.prompt_tokens * self.input_rate + usage.completion_tokens * self.output_rate
        return max(1, math.ceil(raw))

    def as_dict(self) -> dict:
        return {"tier": self.tier, "inputRate": self.input_rate, "outputRate": self.output_rate}


FREE = ModelPolicy("free", FREE_CREDITS_PER_TOKEN, FREE_CREDITS_PER_TOKEN)
PREMIUM = ModelPolicy("premium", PREMIUM_CREDITS_PER_TOKEN, PREMIUM_CREDITS_PER_TOKEN)


def _listed(provider_id: str, model_id: str, entries: frozenset[str]) -> bool:
    """True if an env list names this model, bare or qualified by provider."""
    return model_id in entries or f"{provider_id}:{model_id}" in entries


def tier_for(provider_id: str, model: ModelInfo) -> Tier:
    if _listed(provider_id, model.id, FREE_MODELS):
        return "free"
    if _listed(provider_id, model.id, PREMIUM_MODELS):
        return "premium"
    # The catalog's own speed tier is a fair proxy for cost: "Deep" and
    # "Balanced" are the big models, and for Ollama that label is derived
    # from the parameter count of whatever was pulled.
    return "premium" if model.speed in PREMIUM_SPEEDS else "free"


def policy_for(provider_id: str, model: ModelInfo) -> ModelPolicy:
    return PREMIUM if tier_for(provider_id, model) == "premium" else FREE
