from __future__ import annotations

import os

from providers.openai_provider import OpenAIProvider


class NineRouterProvider(OpenAIProvider):
    """9Router's OpenAI-compatible Chat Completions endpoint."""

    def __init__(self) -> None:
        super().__init__(
            api_key_env="NINEROUTER_API_KEY",
            base_url=os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1"),
            default_model=os.getenv("NINEROUTER_MODEL", "kr/claude-sonnet-4.5"),
        )
