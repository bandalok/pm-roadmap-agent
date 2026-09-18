"""Brief-writer agent — turns the week's analysis into a shareable brief.

The brief is the product. Everything upstream (ingestion, clustering,
trends, scoring) exists so that this artifact is trustworthy: every claim
carries a source count, opportunities stay in RICE order, and caveats are
explicit. The agent assembles a structured context dict from the store —
the model writes prose, but it never sees raw PII beyond what's already
in the feedback, and it can't reorder the rankings.
"""

from __future__ import annotations

from .. import prompts
from ..llm.base import LLMProvider


def build_brief_context(
    *,
    week: str,
    themes: list[dict],
    opportunities: list[dict],
    total_feedback: int,
    date_range: str,
    trend_by_theme: dict[str, dict] | None = None,
) -> dict:
    """Assemble the structured context the brief prompt consumes."""
    trend_by_theme = trend_by_theme or {}
    context_themes = []
    for theme in themes:
        trend = trend_by_theme.get(theme["id"], {})
        context_themes.append(
            {
                "label": theme["label"],
                "description": theme.get("description", ""),
                "count": theme.get("stats", {}).get("count", 0),
                "avg_rating": theme.get("stats", {}).get("avg_rating"),
                "rising": trend.get("rising", False),
                "trend_note": trend.get("trend_note", ""),
            }
        )
    # get_opportunities() keys the theme as "id"; accept either shape.
    opp_by_theme = {o.get("theme_id", o.get("id")): o for o in opportunities}
    context_opps = []
    for theme in themes:
        opp = opp_by_theme.get(theme["id"])
        if not opp:
            continue
        context_opps.append(
            {
                "label": theme["label"],
                "rice": opp["rice"],
                "reach": opp["reach"],
                "impact": opp["impact"],
                "confidence": opp["confidence"],
                "effort": opp["effort"],
            }
        )
    context_opps.sort(key=lambda o: o["rice"], reverse=True)
    return {
        "week": week,
        "themes": context_themes,
        "opportunities": context_opps,
        "total_feedback": total_feedback,
        "date_range": date_range,
    }


def write_brief(
    context: dict,
    provider: LLMProvider,
    *,
    max_tokens: int = 2000,
    temperature: float = 0.4,
) -> str:
    """Generate the Markdown roadmap brief from the week's context."""
    prompt = prompts.brief_prompt(context)
    return provider.complete(
        prompt,
        system=prompts.BRIEF_SYSTEM,
        max_tokens=max_tokens,
        temperature=temperature,
    ).strip()
