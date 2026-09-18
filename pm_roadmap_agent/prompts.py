"""Every LLM prompt the agents use, in one place.

Why centralize prompts?
  1. Prompts are product copy — they deserve review, versioning, and tests
     like any other user-facing surface.
  2. Tuning is iteration: when a theme label comes back vague, the fix
     belongs here, not scattered across agent code.
  3. It makes the PM reasoning explicit. Each prompt documents *why* the
     agent asks for what it asks for, so a PM reading this repo can see the
     product thinking, not just the engineering.

Conventions used below:
  - System prompts set the agent's role and the output contract.
  - User prompts carry the data, numbered so the model can reference items
    by id (ids are stable database keys, never row numbers).
  - Anything we parse as JSON is requested as "a single JSON value",
    and parsing stays defensive in agents/parsing.py regardless.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Theme clustering
# ---------------------------------------------------------------------------
# PM reasoning: raw feedback is noisy and duplicative. The clusterer's job is
# the first pass of "what are users actually telling us" — the same affinity
# mapping a PM does with sticky notes, but at a scale no human sustains.
# We ask for short labels (roadmap-friendly), a one-sentence description
# (so future runs can merge consistently), and representative quotes (so a
# human can sanity-check the cluster without reading everything).

CLUSTER_SYSTEM = """You are a senior product manager doing affinity mapping on user feedback.
Group the feedback items into a small number of clear themes (aim for 4-10 themes
for a batch; fewer is better than more). Every item must be assigned to exactly
one theme — use an "Other / miscellaneous" theme for items that fit nowhere.

For each theme return:
- "label": short, roadmap-friendly name (2-5 words, no jargon)
- "description": one sentence saying what unites the items
- "feedback_ids": the ids of the items in this theme
- "quotes": up to 2 short verbatim quotes that best represent the theme

Respond with a single JSON array of theme objects and nothing else."""


def cluster_prompt(items: list[dict]) -> str:
    """Build the clustering prompt for one batch of feedback items.

    Each item is a dict with at least ``id`` and ``text``; ``rating`` and
    ``created_at`` are included when present to give the model signal about
    severity and recency.
    """
    lines = []
    for item in items:
        meta = []
        if item.get("rating") is not None:
            meta.append(f"rating={item['rating']}")
        if item.get("created_at"):
            meta.append(f"date={item['created_at'][:10]}")
        suffix = f" ({', '.join(meta)})" if meta else ""
        lines.append(f"[{item['id']}] {item['text']}{suffix}")
    numbered = "\n".join(lines)
    return (
        "Group the following user feedback items into themes.\n\n"
        f"{numbered}\n\n"
        "Respond with a single JSON array of theme objects and nothing else."
    )


# ---------------------------------------------------------------------------
# Theme merging (across batches)
# ---------------------------------------------------------------------------
# PM reasoning: we cluster in batches because context windows are finite,
# but batching fragments themes ("app crashes" in batch 1, "stability
# issues" in batch 2). The merge pass reunifies them so trends and scores
# are computed on stable, long-lived themes — the unit a roadmap is built on.

MERGE_SYSTEM = """You are a senior product manager consolidating theme lists produced from
separate batches of user feedback. Merge themes that describe the same underlying
user need or problem into one theme. Keep genuinely distinct themes separate —
do not over-merge.

For each merged theme return:
- "label": short, roadmap-friendly name (2-5 words)
- "description": one sentence saying what unites the theme
- "source_labels": the labels of the input themes that were merged into this one
- "quotes": up to 2 short verbatim quotes carried over from the inputs

Respond with a single JSON array of theme objects and nothing else."""


def merge_prompt(themes: list[dict]) -> str:
    """Build the merge prompt from per-batch theme summaries."""
    lines = []
    for i, theme in enumerate(themes):
        lines.append(
            f"Theme {i}: \"{theme['label']}\" — {theme.get('description', '')}"
        )
        for quote in theme.get("quotes", [])[:2]:
            lines.append(f"    e.g. \"{quote}\"")
    body = "\n".join(lines)
    return (
        "Merge the following themes where they describe the same underlying "
        "user need or problem:\n\n"
        f"{body}\n\n"
        "Respond with a single JSON array of merged theme objects and nothing else."
    )


# ---------------------------------------------------------------------------
# Opportunity scoring (RICE)
# ---------------------------------------------------------------------------
# PM reasoning: themes tell you *what* users say; RICE turns that into a
# *prioritization* conversation. We ask the model to score each factor
# separately with a one-line rationale because a single opaque number hides
# the judgment calls — and judgment calls are what the PM owns. The math
# (R*I*C/E) is deliberately done in code, not by the model, so scoring stays
# auditable and reproducible.

SCORE_SYSTEM = """You are a pragmatic product manager scoring opportunities with the RICE
framework. Score each factor on a 1-10 scale and give a one-line rationale for
each score. Be skeptical: most things are not a 10. Calibrate against the
evidence provided (volume of feedback, ratings, quotes, trend direction).

- reach: how many users this affects (1 = a handful, 10 = nearly everyone)
- impact: how much it moves the needle per user (1 = negligible, 10 = massive)
- confidence: how sure you are about reach and impact (1 = pure guess, 10 = hard data)
- effort: person-weeks of engineering/design effort (1 = trivial, 10 = multi-quarter)

Respond with a single JSON object mapping each theme id to its scores:
{"<theme_id>": {"reach": N, "impact": N, "confidence": N, "effort": N,
               "reach_rationale": "...", "impact_rationale": "...",
               "confidence_rationale": "...", "effort_rationale": "..."}}"""


def score_prompt(themes: list[dict]) -> str:
    """Build the RICE scoring prompt from theme summaries with evidence."""
    blocks = []
    for theme in themes:
        stats = theme.get("stats", {})
        blocks.append(
            f"Theme id: {theme['id']}\n"
            f"Label: {theme['label']}\n"
            f"Description: {theme.get('description', '')}\n"
            f"Evidence: {stats.get('count', 0)} feedback items, "
            f"avg rating {stats.get('avg_rating', 'n/a')}, "
            f"trend: {stats.get('trend', 'stable')}\n"
            "Representative quotes:\n"
            + "\n".join(f"  - \"{q}\"" for q in theme.get("quotes", [])[:3])
        )
    body = "\n\n".join(blocks)
    return (
        "Score each of the following opportunity themes with RICE. "
        "Use the evidence; do not invent facts beyond it.\n\n"
        f"{body}\n\n"
        "Respond with a single JSON object keyed by theme id and nothing else."
    )


# ---------------------------------------------------------------------------
# Roadmap brief
# ---------------------------------------------------------------------------
# PM reasoning: the brief is the artifact a PM actually shares — with
# leadership, with engineering, with design. It must lead with what changed
# (trends), rank what to do (opportunities), and stay honest about evidence
# (source counts on every claim). A brief without counts is just opinion.

BRIEF_SYSTEM = """You are a product leader writing a weekly roadmap brief for the product team.
Write in clear, direct prose — no hype, no filler. Structure the brief exactly as:

# Roadmap Brief — <week>
## What changed this week
## Top themes (with feedback counts)
## Fast-rising themes
## Ranked opportunities
## Suggested next steps
## Caveats

Rules:
- Every claim about user sentiment cites its feedback count.
- Ranked opportunities are ordered by the RICE scores provided — do not reorder.
- Suggested next steps are concrete and small (research, prototype, or experiment).
- Caveats honestly note data limits (sample size, source bias, date range).
- Keep the whole brief under 600 words."""


def brief_prompt(context: dict) -> str:
    """Build the brief prompt from the week's computed context.

    ``context`` carries: week label, date range, theme summaries (label,
    description, count, avg rating, trend, rising flag), ranked opportunities
    with RICE breakdowns, and total feedback ingested.
    """
    lines = [
        f"Week: {context.get('week')}",
        f"Feedback analyzed: {context.get('total_feedback')} items "
        f"({context.get('date_range', 'all time')})",
        "",
        "Themes:",
    ]
    for theme in context.get("themes", []):
        rising = " [RISING]" if theme.get("rising") else ""
        lines.append(
            f"- {theme['label']}{rising}: {theme['count']} items, "
            f"avg rating {theme.get('avg_rating', 'n/a')}. {theme.get('description', '')}"
        )
    lines.append("")
    lines.append("Ranked opportunities (by RICE score):")
    for opp in context.get("opportunities", []):
        lines.append(
            f"- {opp['label']}: RICE {opp['rice']:.1f} "
            f"(reach {opp['reach']}, impact {opp['impact']}, "
            f"confidence {opp['confidence']}, effort {opp['effort']})"
        )
    return "\n".join(lines) + (
        "\n\nWrite the roadmap brief in Markdown following the required structure."
    )
