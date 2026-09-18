"""Tests for the clustering agent with a mocked LLM."""

import json

from pm_roadmap_agent.agents.clustering import cluster_themes
from tests.conftest import FakeProvider


def _cluster_handler(prompt, system):
    # One theme per underlying topic; ids reference the fixture feedback.
    return json.dumps(
        [
            {
                "label": "Crashes",
                "description": "Stability problems",
                "feedback_ids": ["fb_crash_1", "fb_crash_2"],
                "quotes": ["The app crashed twice during my commute"],
            },
            {
                "label": "Pricing",
                "description": "Price complaints",
                "feedback_ids": ["fb_price_1", "fb_price_2"],
                "quotes": ["Too expensive"],
            },
        ]
    )


def _merge_handler(prompt, system):
    # Merge pass keeps both themes (they are distinct).
    return json.dumps(
        [
            {
                "label": "Crashes",
                "description": "Stability problems",
                "source_labels": ["Crashes"],
                "quotes": ["The app crashed twice during my commute"],
            },
            {
                "label": "Pricing",
                "description": "Price complaints",
                "source_labels": ["Pricing"],
                "quotes": ["Too expensive"],
            },
        ]
    )


def test_cluster_themes_end_to_end(feedback_items):
    def handler(prompt, system):
        if "consolidating" in (system or "") or "Merge the following themes" in prompt:
            return _merge_handler(prompt, system)
        return _cluster_handler(prompt, system)

    provider = FakeProvider(handler)
    themes = cluster_themes(feedback_items, provider, batch_size=2)
    labels = {t["label"] for t in themes}
    assert labels == {"Crashes", "Pricing"}
    crashes = next(t for t in themes if t["label"] == "Crashes")
    assert set(crashes["feedback_ids"]) == {"fb_crash_1", "fb_crash_2"}
    # Cluster + merge calls both happened.
    assert len(provider.calls) >= 2


def test_unknown_ids_are_dropped(feedback_items):
    def handler(prompt, system):
        if "Merge the following" in prompt:
            return json.dumps(
                [
                    {
                        "label": "Crashes",
                        "description": "d",
                        "source_labels": ["Crashes"],
                        "quotes": [],
                    }
                ]
            )
        return json.dumps(
            [
                {
                    "label": "Crashes",
                    "description": "d",
                    # fb_ghost does not exist; fb_orphan_test is real but
                    # unassigned by the model -> swept to Uncategorized.
                    "feedback_ids": ["fb_crash_1", "fb_ghost"],
                    "quotes": [],
                }
            ]
        )

    provider = FakeProvider(handler)
    themes = cluster_themes(feedback_items, provider, batch_size=10)
    crashes = next(t for t in themes if t["label"] == "Crashes")
    assert crashes["feedback_ids"] == ["fb_crash_1"]
    uncategorized = next(t for t in themes if t["label"] == "Other / uncategorized")
    assert "fb_ghost" not in uncategorized["feedback_ids"]
    assert set(uncategorized["feedback_ids"]) == {"fb_crash_2", "fb_price_1", "fb_price_2"}


def test_empty_feedback_returns_no_themes():
    provider = FakeProvider(lambda p, s: "[]")
    assert cluster_themes([], provider) == []
    assert provider.calls == []
