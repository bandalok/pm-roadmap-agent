"""Anthropic provider implementation (Claude models)."""

from __future__ import annotations

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Export it or choose another provider."
            )
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "The 'anthropic' package is required for the Anthropic provider. "
                "Install it with: pip install anthropic"
            ) from exc
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        # The Anthropic API has no native JSON mode on every model, so we
        # reinforce the instruction in the prompt itself; parsing stays
        # defensive regardless (see agents.parsing.extract_json).
        user_prompt = prompt
        if json_mode and "JSON" not in prompt:
            user_prompt = prompt + "\n\nRespond with a single JSON value and nothing else."
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
