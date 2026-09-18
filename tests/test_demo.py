"""Offline demo test — the whole pipeline with no API key, in a temp dir."""

import os

from pm_roadmap_agent.demo import run_demo


def test_demo_runs_end_to_end():
    summary = run_demo(keep=False)
    try:
        assert summary["inserted"] > 0
        assert summary["themes"] >= 4  # several keyword themes should hit
        assert summary["opportunities"] == summary["themes"]
        assert summary["brief_path"] and os.path.exists(summary["brief_path"])
        assert os.path.exists(summary["db_path"])
        with open(summary["brief_path"], encoding="utf-8") as fh:
            brief = fh.read()
        for section in ("## Top themes", "## Ranked opportunities", "## Caveats"):
            assert section in brief
        # The synthetic battery spike should be flagged as rising.
        assert summary["rising"], "expected the battery theme to be rising"
    finally:
        import shutil

        shutil.rmtree(summary["workdir"], ignore_errors=True)
