"""Tests for the RICE scoring agent with a mocked LLM."""

import json

from pm_roadmap_agent.agents.scoring import rice_score, score_opportunities
from tests.conftest import FakeProvider


def test_rice_score_math():
    assert rice_score(8, 9, 7, 4) == round(8 * 9 * 7 / 4, 1)
    assert rice_score(1, 1, 1, 10) == 0.1


def _themes():
    return [
        {
            "id": "th_a",
            "label": "Crashes",
            "description": "d",
            "quotes": ["q"],
            "stats": {"count": 10, "avg_rating": 1.5, "trend": "rising"},
        },
        {
            "id": "th_b",
            "label": "Pricing",
            "description": "d",
            "quotes": ["q"],
            "stats": {"count": 4, "avg_rating": 3.0, "trend": "stable"},
        },
    ]


def test_score_opportunities_sorted_and_clamped():
    def handler(prompt, system):
        return json.dumps(
            {
                "th_a": {
                    "reach": 8,
                    "impact": 9,
                    "confidence": 7,
                    "effort": 4,
                    "reach_rationale": "r",
                    "impact_rationale": "i",
                    "confidence_rationale": "c",
                    "effort_rationale": "e",
                },
                # Out-of-range + garbage values must be clamped, not crash.
                "th_b": {
                    "reach": 99,
                    "impact": -3,
                    "confidence": "high",
                    "effort": 0,
                    "reach_rationale": "r",
                    "impact_rationale": "i",
                    "confidence_rationale": "c",
                    "effort_rationale": "e",
                },
            }
        )

    scored = score_opportunities(_themes(), FakeProvider(handler))
    assert [s["theme_id"] for s in scored] == ["th_a", "th_b"]
    assert scored[0]["rice"] == rice_score(8, 9, 7, 4)
    b = scored[1]
    # 99 -> 10, -3 -> 1, "high" -> default 5, 0 -> 1.
    assert (b["reach"], b["impact"], b["confidence"], b["effort"]) == (10, 1, 5, 1)
    assert b["rice"] == rice_score(10, 1, 5, 1)


def test_score_opportunities_empty():
    provider = FakeProvider(lambda p, s: "{}")
    assert score_opportunities([], provider) == []
    assert provider.calls == []
