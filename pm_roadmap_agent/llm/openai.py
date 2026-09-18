"""OpenAI provider implementation (GPT models)."""

from __future__ import annotations

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Export it or choose another provider."
            )
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "The 'openai' package is required for the OpenAI provider. "
                "Install it with: pip install openai"
            ) from exc
        self._client = openai.OpenAI(api_key=api_key)
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
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # Native JSON mode: guarantees a single JSON value back.
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
