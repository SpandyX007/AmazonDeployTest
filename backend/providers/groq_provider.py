"""Groq — OpenAI-compatible, very fast inference over open-weight models."""

from __future__ import annotations

from .base import ModelInfo, register
from .openai_compatible import OpenAICompatibleProvider


@register
class GroqProvider(OpenAICompatibleProvider):
    id = "groq"
    label = "Groq"
    initials = "GQ"
    hue = 24
    setup_hint = "Add GROQ_API_KEY to backend/.env"

    api_key_env = "GROQ_API_KEY"
    base_url = "https://api.groq.com/openai/v1"

    catalog = [
        ModelInfo(
            id="openai/gpt-oss-20b",
            name="GPT-OSS 20B",
            tagline="Balanced open-weight model for everyday chat",
            context="128K",
            speed="Fastest",
        ),
        ModelInfo(
            id="openai/gpt-oss-120b",
            name="GPT-OSS 120B",
            tagline="Bigger sibling — stronger reasoning and code",
            context="128K",
            speed="Balanced",
        ),
        ModelInfo(
            id="llama-3.3-70b-versatile",
            name="Llama 3.3 70B",
            tagline="Versatile generalist with broad world knowledge",
            context="128K",
            speed="Fast",
        ),
        ModelInfo(
            id="llama-3.1-8b-instant",
            name="Llama 3.1 8B",
            tagline="Tiny and instant — great for quick lookups",
            context="128K",
            speed="Fastest",
        ),
        ModelInfo(
            id="deepseek-r1-distill-llama-70b",
            name="DeepSeek R1 Distill",
            tagline="Thinks step by step before answering",
            context="128K",
            speed="Deep",
        ),
        ModelInfo(
            id="qwen/qwen3-32b",
            name="Qwen 3 32B",
            tagline="Strong multilingual and structured output",
            context="131K",
            speed="Fast",
        ),
        ModelInfo(
            id="moonshotai/kimi-k2-instruct",
            name="Kimi K2",
            tagline="Agentic tool use and long-form synthesis",
            context="200K",
            speed="Balanced",
        ),
        ModelInfo(
            id="gemma2-9b-it",
            name="Gemma 2 9B",
            tagline="Lightweight instruction-tuned assistant",
            context="8K",
            speed="Fastest",
        ),
    ]
