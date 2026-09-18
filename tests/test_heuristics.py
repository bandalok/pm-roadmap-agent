"""Tests for the deterministic heuristic agents (demo/offline path)."""

from pm_roadmap_agent.agents.heuristics import (
    heuristic_brief,
    heuristic_cluster,
    heuristic_score,
)


def _items():
    return [
        {"id": "a", "text": "The app crashed twice today, totally broken"},
        {"id": "b", "text": "It keeps freezing on launch, buggy mess"},
        {"id": "c", "text": "Too expensive, the subscription price is too high"},
        {"id": "d", "text": "I love the colors and the pretty interface"},
    ]


def test_heuristic_cluster_assigns_known_themes():
    themes = heuristic_cluster(_items())
    labels = {t["label"] for t in themes}
    assert "App stability & crashes" in labels
    assert "Pricing & subscription" in labels
    crashes = next(t for t in themes if t["label"] == "App stability & crashes")
    assert set(crashes["feedback_ids"]) == {"a", "b"}
    assert crashes["quotes"]  # representative quotes captured


def test_heuristic_cluster_deterministic():
    first = heuristic_cluster(_items())
    second = heuristic_cluster(_items())
    assert [(t["label"], t["feedback_ids"]) for t in first] == [
        (t["label"], t["feedback_ids"]) for t in second
    ]


def test_heuristic_score_rice_math():
    themes = heuristic_cluster(_items())
    stats = {
        t["id"]: {"count": len(t["feedback_ids"]), "avg_rating": 1.5} for t in themes
    }
    scored = heuristic_score(themes, stats)
    assert scored == sorted(scored, key=lambda s: s["rice"], reverse=True)
    for s in scored:
        expected = round((s["reach"] * s["impact"] * s["confidence"]) / s["effort"], 1)
        assert s["rice"] == expected
        assert all(1 <= s[k] <= 10 for k in ("reach", "impact", "confidence", "effort"))


def test_heuristic_brief_renders_sections():
    context = {
        "week": "2026-W37",
        "total_feedback": 4,
        "date_range": "2026-09-01 to 2026-09-07",
        "themes": [
            {
                "label": "App stability & crashes",
                "count": 2,
                "avg_rating": 1.5,
                "rising": True,
                "trend_note": "2 mentions vs ~0.0/week before",
            }
        ],
        "opportunities": [
            {
                "label": "App stability & crashes",
                "rice": 21.6,
                "reach": 2,
                "impact": 7,
                "confidence": 6,
                "effort": 8,
            }
        ],
    }
    brief = heuristic_brief(context)
    for section in (
        "# Roadmap Brief — 2026-W37",
        "## What changed this week",
        "## Top themes",
        "## Ranked opportunities",
        "## Suggested next steps",
        "## Caveats",
    ):
        assert section in brief
    assert "App stability & crashes" in brief
