"""One-command offline demo: the whole pipeline, no API key.

Runs ingest → cluster → trends → score → brief on the bundled synthetic
sample (``data/sample_feedback.csv``) using the deterministic heuristic
agents. Writes to a scratch SQLite database and ``briefs/`` inside a
temporary directory by default, so it never touches your real data.

Usage:
    python -m pm_roadmap_agent --demo
    python -m pm_roadmap_agent.demo --keep   # keep outputs under ./demo-output
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

from .config import Config
from .ingestors.csv_ingestor import CSVIngestor
from .pipeline import run_pipeline
from .store import Store

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)
SAMPLE_CSV = os.path.join(PROJECT_DIR, "data", "sample_feedback.csv")


def run_demo(keep: bool = False) -> dict:
    """Execute the demo pipeline; returns the summary plus output paths."""
    if keep:
        workdir = os.path.join(os.getcwd(), "demo-output")
        os.makedirs(workdir, exist_ok=True)
    else:
        workdir = tempfile.mkdtemp(prefix="pm-roadmap-agent-demo-")

    db_path = os.path.join(workdir, "demo.db")
    briefs_dir = os.path.join(workdir, "briefs")
    config = Config()
    config.db_path = db_path
    config.briefs_dir = briefs_dir

    store = Store(db_path)
    try:
        ingestor = CSVIngestor(
            SAMPLE_CSV,
            text_column="text",
            author_column="author",
            rating_column="rating",
            created_at_column="created_at",
            source_label="demo:sample-app",
        )
        summary = run_pipeline(
            config, ingestors=[ingestor], use_heuristics=True, store=store
        )
    finally:
        store.close()

    summary["workdir"] = workdir
    summary["db_path"] = db_path
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline demo pipeline.")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep outputs under ./demo-output instead of a temp dir.",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(SAMPLE_CSV):
        print(f"Sample data not found: {SAMPLE_CSV}", file=sys.stderr)
        return 1

    print("PM Roadmap Agent — offline demo")
    print(f"Sample data : {SAMPLE_CSV}")
    summary = run_demo(keep=args.keep)
    print(f"Feedback    : {summary['inserted']} inserted, {summary['skipped']} skipped")
    print(f"Themes      : {summary['themes']}")
    print(f"Opportunities: {summary['opportunities']}")
    if summary.get("rising"):
        print(f"Rising      : {', '.join(summary['rising'])}")
    print(f"Brief       : {summary['brief_path']}")
    print(f"Workdir     : {summary['workdir']}")
    if summary["brief_path"]:
        print()
        print("=" * 60)
        with open(summary["brief_path"], encoding="utf-8") as fh:
            print(fh.read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
