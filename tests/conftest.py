"""Shared test doubles and fixtures."""

from __future__ import annotations

import pytest

from pm_roadmap_agent.llm.base import LLMProvider
from pm_roadmap_agent.store import Store


class FakeProvider(LLMProvider):
    """Deterministic stand-in for an LLM backend.

    ``handler`` receives (prompt, system) and returns the raw model text.
    Every call is recorded for assertions.
    """

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        return self.handler(prompt, system)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def feedback_items():
    """Small hand-written feedback set with known ids."""
    return [
        {
            "id": "fb_crash_1",
            "source": "test",
            "text": "The app crashed twice during my commute this morning",
            "author": "a",
            "rating": 1,
            "created_at": "2026-09-01T10:00:00+00:00",
        },
        {
            "id": "fb_crash_2",
            "source": "test",
            "text": "It keeps freezing on the home screen",
            "author": "b",
            "rating": 2,
            "created_at": "2026-09-02T10:00:00+00:00",
        },
        {
            "id": "fb_price_1",
            "source": "test",
            "text": "Too expensive for what you get each month",
            "author": "c",
            "rating": 2,
            "created_at": "2026-09-03T10:00:00+00:00",
        },
        {
            "id": "fb_price_2",
            "source": "test",
            "text": "The subscription price is too high",
            "author": "d",
            "rating": 3,
            "created_at": "2026-09-04T10:00:00+00:00",
        },
    ]
