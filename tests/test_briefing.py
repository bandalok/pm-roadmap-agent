"""Tests for the brief context builder (LLM briefing agent's input)."""

from pm_roadmap_agent.agents.briefing import build_brief_context, write_brief
from tests.conftest import FakeProvider


def test_build_brief_context_orders_opportunities_by_rice():
    themes = [
        {"id": "t1", "label": "Crashes", "description": "d", "stats": {"count": 5, "avg_rating": 1.0}},
        {"id": "t2", "label": "Pricing", "description": "d", "stats": {"count": 3, "avg_rating": 3.0}},
    ]
    opportunities = [
        {"theme_id": "t1", "rice": 50.0, "reach": 8, "impact": 8, "confidence": 5, "effort": 5},
        {"theme_id": "t2", "rice": 90.0, "reach": 9, "impact": 8, "confidence": 7, "effort": 4},
    ]
    ctx = build_brief_context(
        week="2026-W37",
        themes=themes,
        opportunities=opportunities,
        total_feedback=8,
        date_range="2026-09-01 to 2026-09-07",
        trend_by_theme={"t1": {"rising": True, "trend_note": "spike"}},
    )
    assert ctx["week"] == "2026-W37"
    assert [o["label"] for o in ctx["opportunities"]] == ["Pricing", "Crashes"]
    assert ctx["themes"][0]["rising"] is True
    assert ctx["total_feedback"] == 8


def test_write_brief_uses_prompt_and_system():
    provider = FakeProvider(lambda p, s: "# Brief\n\nDone.")
    out = write_brief({"week": "x"}, provider)
    assert out == "# Brief\n\nDone."
    assert "roadmap brief" in provider.calls[0]["system"].lower()
