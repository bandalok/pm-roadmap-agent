"""Provider factory — picks the configured backend from the environment."""

from __future__ import annotations

from ..config import Config
from .anthropic import AnthropicProvider
from .base import LLMProvider
from .openai import OpenAIProvider

__all__ = ["LLMProvider", "get_provider"]


def get_provider(config: Config | None = None) -> LLMProvider:
    """Build the LLM provider named by ``LLM_PROVIDER`` (default: anthropic)."""
    config = config or Config()
    name = config.llm_provider
    model = config.default_model
    if name == "openai":
        return OpenAIProvider(api_key=config.openai_api_key, model=model)
    if name == "anthropic":
        return AnthropicProvider(api_key=config.anthropic_api_key, model=model)
    raise ValueError(
        f"Unknown LLM_PROVIDER {name!r}. Expected 'anthropic' or 'openai'."
    )
