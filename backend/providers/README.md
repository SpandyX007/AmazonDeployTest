# Adding an LLM provider

The API layer never names a vendor — it resolves everything through the
registry in [`__init__.py`](__init__.py). Adding one is two steps.

## 1. Write the module

**If the vendor speaks the OpenAI chat-completions format** (most do:
OpenRouter, Together, Fireworks, DeepSeek, vLLM, LM Studio, …) subclass
`OpenAICompatibleProvider` and you're done in ~20 lines:

```python
# backend/providers/openrouter_provider.py
from .base import ModelInfo, register
from .openai_compatible import OpenAICompatibleProvider


@register
class OpenRouterProvider(OpenAICompatibleProvider):
    id = "openrouter"            # wire slug
    label = "OpenRouter"         # shown in the picker
    initials = "OR"              # badge
    hue = 338                    # 0-360, drives the accent colour
    setup_hint = "Add OPENROUTER_API_KEY to backend/.env"

    api_key_env = "OPENROUTER_API_KEY"
    base_url = "https://openrouter.ai/api/v1"

    catalog = [
        ModelInfo(
            id="anthropic/claude-sonnet-4.5",
            name="Claude Sonnet 4.5",
            tagline="Strong coding and long-context reasoning",
            context="200K",
            speed="Balanced",     # Fastest | Fast | Balanced | Deep
        ),
    ]
```

**Otherwise** subclass `Provider` from [`base.py`](base.py) and implement
`status()`, `models()` and `stream()` — see
[`ollama_provider.py`](ollama_provider.py), which discovers its catalog from
the local daemon instead of hard-coding one.

Two rules keep the service healthy:

- **Never raise at import time.** A missing key must make `status()` return
  `ProviderStatus(False, "…")`, not crash the app — other providers keep working.
- **Build clients lazily**, inside a method, for the same reason.

### Report usage, or the turn gets estimated

`stream()` yields text chunks and then, last, one `Usage(prompt_tokens,
completion_tokens)` if the vendor reports counts. That `Usage` is what the
account is billed on; without it the server charges an estimate from
character lengths and flags the ledger row `estimated`. Vendors do report
it — it is usually on the final chunk — so find where yours puts it:

- OpenAI-format APIs: `stream_options={"include_usage": True}` → `chunk.usage`
  (already handled by `OpenAICompatibleProvider`).
- Ollama: `prompt_eval_count` / `eval_count` on the `done: true` chunk.

Honour `max_output_tokens` too — it is the cap that stops one reply from
overdrawing a nearly-empty balance by more than a known amount.

### Tier and price come from the catalog

`speed` is not just a label: by default a model whose speed is `Balanced` or
`Deep` is **premium** (locked until the account pays, billed at
`PREMIUM_CREDITS_PER_TOKEN`), and `Fastest`/`Fast` is free tier. Set it
honestly. The owner can override any single model with `PREMIUM_MODELS` /
`FREE_MODELS` in `.env` — see [`../pricing.py`](../pricing.py).

## 2. Register it

Add one import to the marked block in [`__init__.py`](__init__.py):

```python
from . import openrouter_provider  # noqa: E402,F401
```

That's it. `GET /api/providers` now includes it, the frontend picker renders it
from that response, and `/api/chat/stream` can route to it. No frontend change
is required.
