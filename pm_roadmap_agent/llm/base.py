"""LLM provider abstraction.

The agents never talk to a vendor SDK directly — they talk to this small
interface. That keeps every prompt, parser, and retry in one place and
lets the pipeline run on Anthropic, OpenAI, a test double, or anything
else that implements ``complete()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Minimal contract every model backend must satisfy."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        """Return the model's raw text response for ``prompt``.

        When ``json_mode`` is true the provider should steer the model
        toward emitting a single JSON value (via native JSON mode where
        supported, otherwise via instruction). Callers still parse
        defensively — see ``pm_roadmap_agent.agents.parsing``.
        """
        raise NotImplementedError
