"""Tests for the trend tracker: weekly bucketing and spike detection."""

from pm_roadmap_agent.agents.trends import (
    compute_weekly_counts,
    detect_rising,
    iso_week,
    track_trends,
)


def test_iso_week():
    assert iso_week("2026-09-16T10:00:00+00:00") == "2026-W38"
    assert iso_week(None) is None
    assert iso_week("not-a-date") is None


def test_compute_weekly_counts():
    items = [
        {"created_at": "2026-09-01T10:00:00+00:00"},
        {"created_at": "2026-09-02T10:00:00+00:00"},
        {"created_at": "2026-09-09T10:00:00+00:00"},
        {"created_at": None},
    ]
    assert compute_weekly_counts(items) == {"2026-W36": 2, "2026-W37": 1}


def test_detect_rising_spike():
    rising, note = detect_rising(
        {"2026-W34": 1, "2026-W35": 1, "2026-W36": 2, "2026-W37": 8},
        min_count=3,
        growth_factor=2.0,
    )
    assert rising is True
    assert "2026-W37" in note


def test_detect_rising_stable():
    rising, _ = detect_rising(
        {"2026-W34": 4, "2026-W35": 5, "2026-W36": 4, "2026-W37": 5},
        min_count=3,
        growth_factor=2.0,
    )
    assert rising is False


def test_detect_rising_below_min_count():
    rising, _ = detect_rising(
        {"2026-W36": 0, "2026-W37": 2}, min_count=3, growth_factor=2.0
    )
    assert rising is False


def test_track_trends_persists_snapshots(store):
    items = [
        {"id": "x1", "created_at": "2026-09-01T10:00:00+00:00"},
        {"id": "x2", "created_at": "2026-09-02T10:00:00+00:00"},
        {"id": "x3", "created_at": "2026-09-09T10:00:00+00:00"},
    ]
    result = track_trends(store, "th_x", items, min_count=1, growth_factor=2.0)
    snaps = {s["week"]: s["feedback_count"] for s in store.get_snapshots("th_x")}
    assert snaps == {"2026-W36": 2, "2026-W37": 1}
    assert result["rising"] is False  # 1 vs baseline 2
    assert result["weekly_counts"] == snaps
