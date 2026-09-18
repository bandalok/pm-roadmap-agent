"""Opportunity-scoring agent (LLM-backed RICE).

The agent asks the model to score reach / impact / confidence / effort
(1-10) with a one-line rationale per factor, then computes RICE in code:

    RICE = (reach × impact × confidence) / effort

Why the model doesn't do the math: arithmetic is the easy part, and doing
it in code makes every score reproducible and auditable — the brief can
show the exact inputs behind each ranking. The model contributes judgment
(calibrated against the evidence we pass in); the code contributes the
formula. Scores are validated (ints, 1-10) and fall back to safe defaults
rather than failing the run on one malformed response.
"""

from __future__ import annotations

from .. import prompts
from ..llm.base import LLMProvider
from .parsing import extract_json


def _clamp(value, default: int = 5) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(10, number))


def rice_score(reach: int, impact: int, confidence: int, effort: int) -> float:
    """RICE = (R × I × C) / E, rounded to one decimal."""
    return round((reach * impact * confidence) / max(effort, 1), 1)


def score_opportunities(
    themes: list[dict],
    provider: LLMProvider,
    *,
    max_tokens: int = 2000,
    temperature: float = 0.2,
) -> list[dict]:
    """Score themes with RICE. Each theme dict needs ``id``, ``label``,
    ``description``, ``quotes``, and a ``stats`` dict (count, avg_rating,
    trend). Returns score dicts sorted by RICE descending, ready for
    ``Store.save_scores``.
    """
    if not themes:
        return []
    prompt = prompts.score_prompt(themes)
    raw = provider.complete(
        prompt,
        system=prompts.SCORE_SYSTEM,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=True,
    )
    parsed = extract_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Scoring model did not return a JSON object")

    scored = []
    for theme in themes:
        entry = parsed.get(theme["id"], {})
        reach = _clamp(entry.get("reach"))
        impact = _clamp(entry.get("impact"))
        confidence = _clamp(entry.get("confidence"))
        effort = _clamp(entry.get("effort"))
        scored.append(
            {
                "theme_id": theme["id"],
                "reach": reach,
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "rice": rice_score(reach, impact, confidence, effort),
                "rationales": {
                    "reach": str(entry.get("reach_rationale", "")),
                    "impact": str(entry.get("impact_rationale", "")),
                    "confidence": str(entry.get("confidence_rationale", "")),
                    "effort": str(entry.get("effort_rationale", "")),
                },
            }
        )
    scored.sort(key=lambda s: s["rice"], reverse=True)
    return scored
