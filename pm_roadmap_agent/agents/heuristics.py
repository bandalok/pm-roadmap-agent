"""Deterministic heuristic agents for offline / demo mode.

When no LLM key is available (``--demo``, CI, quick experiments), the
pipeline swaps the LLM agents for these. They are intentionally simple and
fully deterministic:

- clustering: keyword-seed matching against a small, legible taxonomy.
  A real PM can read the keyword lists and immediately judge whether the
  taxonomy fits their product — and extend it.
- scoring: volume- and rating-derived RICE inputs with fixed confidence.
  Transparent by construction; the brief says exactly how numbers were
  derived.
- briefing: a template brief (no prose generation), so ``--demo`` output
  is byte-identical across runs.

Nothing here pretends to be as good as the LLM path; it exists so anyone
can run the whole system end to end in one command.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter

# Each entry: (theme label, one-line description, keyword seeds).
# Ordered by specificity — the first matching group wins, so put the most
# distinctive themes first.
KEYWORD_THEMES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "App stability & crashes",
        "The app crashes, freezes, or behaves erratically.",
        ("crash", "crashes", "crashed", "freeze", "freezes", "froze", "frozen",
         "bug", "buggy", "broken", "glitch", "glitchy", "force close"),
    ),
    (
        "Battery & overheating",
        "The app drains battery or makes the device hot.",
        ("battery", "drain", "drains", "draining", "overheat", "overheating", "hot"),
    ),
    (
        "Performance & loading",
        "Slow loads, lag, buffering, or stuttering playback.",
        ("slow", "lag", "laggy", "loading", "loads", "buffer", "buffering",
         "stutter", "stuttering", "takes forever"),
    ),
    (
        "Offline & downloads",
        "Offline mode, downloads, and listening without connectivity.",
        ("offline", "download", "downloads", "downloaded", "plane", "flight",
         "no internet", "no signal", "subway"),
    ),
    (
        "Pricing & subscription",
        "Price, plans, trials, and subscription value.",
        ("price", "pricing", "expensive", "cost", "costs", "subscription",
         "subscribe", "pay", "paid", "premium", "trial", "money", "worth it"),
    ),
    (
        "Design & usability",
        "Visual design, layout, navigation, and ease of use.",
        ("design", "ui", "ux", "layout", "confusing", "cluttered", "ugly",
         "font", "dark mode", "navigation", "navigate", "redesign", "look"),
    ),
    (
        "Feature requests",
        "Explicit asks for new capabilities.",
        ("wish", "want", "add", "feature", "request", "please", "need",
         "should have", "would love", "missing"),
    ),
    (
        "Account & support",
        "Login, accounts, refunds, and customer support.",
        ("login", "log in", "account", "password", "support", "refund",
         "customer service", "help", "sign up", "signup"),
    ),
]

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def heuristic_cluster(feedback: list[dict]) -> list[dict]:
    """Assign each feedback item to the best keyword-matching theme.

    Deterministic: fixed taxonomy, first-match-wins on ties, stable order.
    Returns theme dicts in the same shape as the LLM clusterer.
    """
    buckets: dict[str, list[str]] = {label: [] for label, _, _ in KEYWORD_THEMES}
    buckets["Other / uncategorized"] = []
    quotes: dict[str, list[str]] = {label: [] for label in buckets}

    for item in feedback:
        words = _words(item["text"])
        lowered = item["text"].lower()
        best_label = "Other / uncategorized"
        best_hits = 0
        for label, _, seeds in KEYWORD_THEMES:
            hits = sum(1 for seed in seeds if seed in lowered or seed in words)
            if hits > best_hits:
                best_hits = hits
                best_label = label
        buckets[best_label].append(item["id"])
        if len(quotes[best_label]) < 2 and len(item["text"]) <= 220:
            quotes[best_label].append(item["text"])

    by_label = {label: desc for label, desc, _ in KEYWORD_THEMES}
    by_label["Other / uncategorized"] = "Feedback items that did not fit a named theme."
    themes = []
    for label, ids in buckets.items():
        if not ids:
            continue
        themes.append(
            {
                "id": f"th_{uuid.uuid4().hex[:12]}",
                "label": label,
                "description": by_label[label],
                "feedback_ids": sorted(ids),
                "quotes": quotes[label],
            }
        )
    return themes


# Effort priors for the demo scorer: a PM's rough t-shirt sizing per theme.
# Documented and overridable — the point is that effort is an *input* from
# product judgment, not something the data can tell you.
DEMO_EFFORT = {
    "App stability & crashes": 8,
    "Battery & overheating": 7,
    "Performance & loading": 6,
    "Offline & downloads": 7,
    "Pricing & subscription": 3,
    "Design & usability": 5,
    "Feature requests": 5,
    "Account & support": 4,
    "Other / uncategorized": 5,
}


def heuristic_score(themes: list[dict], stats_by_theme: dict[str, dict]) -> list[dict]:
    """Deterministic RICE scoring from volume and rating evidence.

    - reach: scaled from item count (1-10)
    - impact: from average rating deficit — lower-rated themes hurt more
    - confidence: fixed at 6 ("medium — heuristic evidence only")
    - effort: from DEMO_EFFORT priors
    """
    scored = []
    for theme in themes:
        stats = stats_by_theme.get(theme["id"], {})
        count = stats.get("count", 0)
        avg_rating = stats.get("avg_rating")
        reach = max(1, min(10, 1 + count // 2))
        if avg_rating is None:
            impact = 5
        else:
            # 5-star scale: a 1-star average is maximum pain.
            impact = max(1, min(10, int(round((5.0 - avg_rating) * 2))))
        confidence = 6
        effort = DEMO_EFFORT.get(theme["label"], 5)
        rice = round((reach * impact * confidence) / effort, 1)
        scored.append(
            {
                "theme_id": theme["id"],
                "reach": reach,
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "rice": rice,
                "rationales": {
                    "reach": f"based on {count} feedback items (demo heuristic)",
                    "impact": (
                        f"average rating {avg_rating} signals user pain (demo heuristic)"
                        if avg_rating is not None
                        else "no ratings in sample (demo heuristic)"
                    ),
                    "confidence": "medium: heuristic evidence only, no LLM judgment (demo)",
                    "effort": f"t-shirt prior for '{theme['label']}' (demo default)",
                },
            }
        )
    scored.sort(key=lambda s: s["rice"], reverse=True)
    return scored


def heuristic_brief(context: dict) -> str:
    """Render the roadmap brief from a template (no LLM prose)."""
    lines = [
        f"# Roadmap Brief — {context.get('week', 'demo')}",
        "",
        f"_Generated offline by the heuristic demo pipeline from "
        f"{context.get('total_feedback', 0)} feedback items "
        f"({context.get('date_range', 'sample data')})._",
        "",
        "## What changed this week",
        "",
    ]
    rising = [t for t in context.get("themes", []) if t.get("rising")]
    if rising:
        for theme in rising:
            lines.append(
                f"- **{theme['label']}** is rising — {theme.get('trend_note', '')} "
                f"({theme['count']} total mentions)."
            )
    else:
        lines.append("- No theme is spiking this week; volume is broadly stable.")
    lines += ["", "## Top themes", ""]
    for theme in sorted(context.get("themes", []), key=lambda t: t["count"], reverse=True):
        flag = " 🔺 rising" if theme.get("rising") else ""
        lines.append(
            f"- **{theme['label']}**{flag} — {theme['count']} items"
            + (
                f", avg rating {theme['avg_rating']}"
                if theme.get("avg_rating") is not None
                else ""
            )
        )
    lines += ["", "## Ranked opportunities", ""]
    for i, opp in enumerate(context.get("opportunities", []), 1):
        lines.append(
            f"{i}. **{opp['label']}** — RICE {opp['rice']:.1f} "
            f"(reach {opp['reach']}, impact {opp['impact']}, "
            f"confidence {opp['confidence']}, effort {opp['effort']})"
        )
    lines += ["", "## Suggested next steps", ""]
    for opp in context.get("opportunities", [])[:3]:
        lines.append(
            f"- Validate **{opp['label']}** with 5 targeted user interviews "
            f"before committing engineering."
        )
    lines += [
        "",
        "## Caveats",
        "",
        "- Demo output: themes, scores, and copy are heuristic, not LLM-judged.",
        "- Sample data is synthetic and small; treat counts as illustrative.",
        "- Effort priors are defaults — replace with your team's estimates.",
        "",
    ]
    return "\n".join(lines)


def weekly_counts(feedback: list[dict]) -> Counter:
    """Count feedback per ISO week (helper shared by trends + brief)."""
    counts: Counter = Counter()
    for item in feedback:
        created = item.get("created_at")
        if created:
            counts[created[:10]] += 1
    return counts
