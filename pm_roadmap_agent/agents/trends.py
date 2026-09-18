"""Trend tracker — theme volume over time, with spike detection.

PM reasoning: a theme with 50 mentions accumulated over a year is backlog;
the same 50 mentions arriving in the last 7 days is a fire. Raw counts
don't distinguish those — *velocity* does. This module buckets each
theme's feedback by ISO week, persists the snapshots (so history survives
across runs), and flags themes whose latest week grew sharply against
their recent baseline.

The detector is intentionally simple and transparent (no black-box
anomaly model): a theme is "rising" when its latest full week has at
least ``min_count`` items AND at least ``growth_factor``x the mean of the
preceding up-to-3 weeks. A PM can read that rule, disagree with it, and
tune it via config — which is the point.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date


def iso_week(created_at: str | None) -> str | None:
    """Map an ISO timestamp to its ISO week label, e.g. '2026-W37'."""
    if not created_at:
        return None
    try:
        day = date.fromisoformat(created_at[:10])
    except ValueError:
        return None
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def compute_weekly_counts(feedback: list[dict]) -> dict[str, int]:
    """Count feedback items per ISO week (ignores undated items)."""
    counts: dict[str, int] = defaultdict(int)
    for item in feedback:
        week = iso_week(item.get("created_at"))
        if week:
            counts[week] += 1
    return dict(counts)


def detect_rising(
    weekly_counts: dict[str, int],
    *,
    min_count: int = 3,
    growth_factor: float = 2.0,
    baseline_weeks: int = 3,
) -> tuple[bool, str]:
    """Decide whether the latest week is spiking.

    Returns (is_rising, human-readable note explaining the call).
    """
    if not weekly_counts:
        return False, "no dated feedback"
    weeks = sorted(weekly_counts)
    latest = weeks[-1]
    latest_count = weekly_counts[latest]
    baseline_vals = [weekly_counts[w] for w in weeks[-(baseline_weeks + 1) : -1]]
    if not baseline_vals:
        # Single week of data: rising iff it clears the volume bar.
        if latest_count >= min_count:
            return True, f"{latest_count} mentions in {latest} (first week of data)"
        return False, f"only {latest_count} mentions in {latest}"
    baseline = sum(baseline_vals) / len(baseline_vals)
    if latest_count >= min_count and latest_count >= growth_factor * max(baseline, 1):
        return (
            True,
            f"{latest_count} mentions in {latest} vs ~{baseline:.1f}/week before",
        )
    return False, f"{latest_count} in {latest} vs ~{baseline:.1f}/week baseline"


def track_trends(
    store,
    theme_id: str,
    feedback: list[dict],
    *,
    min_count: int = 3,
    growth_factor: float = 2.0,
) -> dict:
    """Persist this run's weekly snapshots and report the trend verdict."""
    counts = compute_weekly_counts(feedback)
    for week, count in counts.items():
        store.save_snapshot(theme_id, week, count)
    history = {s["week"]: s["feedback_count"] for s in store.get_snapshots(theme_id)}
    rising, note = detect_rising(
        history, min_count=min_count, growth_factor=growth_factor
    )
    return {"rising": rising, "trend_note": note, "weekly_counts": history}
