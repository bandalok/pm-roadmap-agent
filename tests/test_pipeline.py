"""End-to-end pipeline test with a fully mocked LLM."""

import json
import os
import re

import pytest

import pm_roadmap_agent.pipeline as pipeline_mod
from pm_roadmap_agent.config import Config
from pm_roadmap_agent.pipeline import run_pipeline
from tests.conftest import FakeProvider


def _fake_llm(prompt, system):
    system = system or ""
    if "roadmap brief" in system:
        return "# Roadmap Brief — test\n\n## What changed this week\n\n- Test content.\n"
    if "RICE" in system:
        ids = re.findall(r"Theme id: (\S+)", prompt)
        return json.dumps(
            {
                tid: {
                    "reach": 6,
                    "impact": 7,
                    "confidence": 5,
                    "effort": 3,
                    "reach_rationale": "r",
                    "impact_rationale": "i",
                    "confidence_rationale": "c",
                    "effort_rationale": "e",
                }
                for tid in ids
            }
        )
    if "Merge the following themes" in prompt:
        return json.dumps(
            [
                {
                    "label": "Crashes",
                    "description": "Stability problems",
                    "source_labels": ["Crashes"],
                    "quotes": ["The app crashed twice"],
                },
                {
                    "label": "Pricing",
                    "description": "Price complaints",
                    "source_labels": ["Pricing"],
                    "quotes": ["Too expensive"],
                },
            ]
        )
    # Cluster prompt.
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
                "quotes": ["Too expensive for what you get"],
            },
        ]
    )


def test_full_pipeline_llm_path(store, feedback_items, tmp_path, monkeypatch):
    store.add_feedback(feedback_items)
    monkeypatch.setattr(
        pipeline_mod, "get_provider", lambda config: FakeProvider(_fake_llm)
    )
    config = Config()
    config.briefs_dir = str(tmp_path / "briefs")

    summary = run_pipeline(config, ingestors=[], use_heuristics=False, store=store)

    # Feedback was seeded directly into the store (no ingestors), so the
    # pipeline inserts 0 new rows but analyzes the 4 seeded items.
    assert summary["inserted"] == 0
    assert summary["skipped"] == 0
    assert summary["themes"] == 2
    assert summary["opportunities"] == 2
    assert summary["brief_path"] and os.path.exists(summary["brief_path"])
    with open(summary["brief_path"]) as fh:
        assert "Roadmap Brief" in fh.read()

    # Themes persisted with evidence links; scores ranked.
    themes = store.get_themes()
    assert {t["label"] for t in themes} == {"Crashes", "Pricing"}
    opps = store.get_opportunities(run_id=summary["run_id"])
    assert len(opps) == 2
    assert opps[0]["rice"] >= opps[1]["rice"]
    # Trend snapshots were recorded for dated feedback.
    assert store.get_snapshots(themes[0]["id"])


def test_pipeline_with_no_feedback(store, tmp_path):
    config = Config()
    config.briefs_dir = str(tmp_path / "briefs")
    summary = run_pipeline(
        config, ingestors=[], use_heuristics=True, store=store
    )
    assert summary["themes"] == 0
    assert summary["brief_path"] is None
