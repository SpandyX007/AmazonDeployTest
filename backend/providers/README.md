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

## 2. Register it

Add one import to the marked block in [`__init__.py`](__init__.py):

```python
from . import openrouter_provider  # noqa: E402,F401
```

That's it. `GET /api/providers` now includes it, the frontend picker renders it
from that response, and `/api/chat/stream` can route to it. No frontend change
is required.
