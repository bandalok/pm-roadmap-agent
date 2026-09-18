"""Pipeline orchestration — the full feedback → roadmap run.

Stages:
  1. ingest      — pull feedback from every configured ingestor
  2. store       — normalize + dedupe into SQLite (idempotent)
  3. cluster     — LLM affinity-mapping into themes (or heuristic offline)
  4. trends      — per-week volume snapshots + spike detection
  5. score       — RICE scoring per theme (or heuristic offline)
  6. brief       — Markdown roadmap brief, saved to BRIEFS_DIR

``run_pipeline`` is the single entry point used by the CLI, the digest,
the demo, and the Streamlit UI. ``use_heuristics=True`` selects the
deterministic offline path (no API key); otherwise an LLM provider is
required.
"""

from __future__ import annotations

import os
from datetime import date

from .agents import briefing, clustering, heuristics, scoring, trends
from .config import Config
from .llm import get_provider
from .store import Store


def _current_week_label() -> str:
    today = date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def run_pipeline(
    config: Config | None = None,
    ingestors: list | None = None,
    *,
    use_heuristics: bool = False,
    store: Store | None = None,
) -> dict:
    """Execute the full pipeline. Returns a summary dict for callers/UIs."""
    config = config or Config()
    own_store = store is None
    store = store or Store(config.db_path)
    try:
        return _run(config, store, ingestors or [], use_heuristics)
    finally:
        if own_store:
            store.close()


def _run(config: Config, store: Store, ingestors: list, use_heuristics: bool) -> dict:
    run_id = store.create_run(
        {
            "provider": "heuristic" if use_heuristics else config.llm_provider,
            "model": "heuristic" if use_heuristics else config.default_model,
            "ingestors": [getattr(i, "name", type(i).__name__) for i in ingestors],
        }
    )

    # 1-2. Ingest + dedupe.
    fetched: list[dict] = []
    for ingestor in ingestors:
        fetched.extend(ingestor.fetch())
    fetched = fetched[: config.max_feedback_per_run]
    inserted, skipped = store.add_feedback(fetched)
    feedback = store.get_feedback(limit=config.max_feedback_per_run)
    if not feedback:
        return {
            "run_id": run_id,
            "inserted": inserted,
            "skipped": skipped,
            "themes": 0,
            "brief_path": None,
            "note": "No feedback ingested; nothing to analyze.",
        }

    provider = None if use_heuristics else get_provider(config)

    # 3. Cluster into themes.
    if use_heuristics:
        theme_dicts = heuristics.heuristic_cluster(feedback)
    else:
        theme_dicts = clustering.cluster_themes(
            feedback,
            provider,
            batch_size=config.cluster_batch_size,
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
        )
    theme_ids = store.save_themes(run_id, theme_dicts)
    themes = [store.get_theme(tid) for tid in theme_ids]

    # Attach per-theme evidence for downstream agents.
    by_id = {f["id"]: f for f in feedback}
    trend_by_theme: dict[str, dict] = {}
    for theme, tdict in zip(themes, theme_dicts):
        items = [by_id[fid] for fid in tdict.get("feedback_ids", []) if fid in by_id]
        stats = store.theme_stats(theme["id"])
        theme["stats"] = stats
        theme["quotes"] = tdict.get("quotes", [])
        # 4. Trends (persisted snapshots + spike verdict).
        trend_by_theme[theme["id"]] = trends.track_trends(
            store,
            theme["id"],
            items,
            min_count=config.trend_min_count,
            growth_factor=config.trend_growth_factor,
        )
        stats["trend"] = (
            "rising" if trend_by_theme[theme["id"]]["rising"] else "stable"
        )

    # 5. Score opportunities.
    if use_heuristics:
        stats_by_theme = {t["id"]: t["stats"] for t in themes}
        scored = heuristics.heuristic_score(theme_dicts, stats_by_theme)
    else:
        scored = scoring.score_opportunities(
            themes,
            provider,
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
        )
    store.save_scores(run_id, scored)

    # 6. Write the brief.
    week = _current_week_label()
    dates = sorted(f["created_at"] for f in feedback if f.get("created_at"))
    date_range = f"{dates[0][:10]} to {dates[-1][:10]}" if dates else "undated sample"
    opportunities = store.get_opportunities(run_id=run_id)
    context = briefing.build_brief_context(
        week=week,
        themes=themes,
        opportunities=opportunities,
        total_feedback=len(feedback),
        date_range=date_range,
        trend_by_theme=trend_by_theme,
    )
    if use_heuristics:
        brief_md = heuristics.heuristic_brief(context)
    else:
        brief_md = briefing.write_brief(
            context,
            provider,
            max_tokens=config.llm_max_tokens,
            temperature=0.4,
        )

    os.makedirs(config.briefs_dir, exist_ok=True)
    brief_path = os.path.join(config.briefs_dir, f"roadmap-brief-{week}.md")
    with open(brief_path, "w", encoding="utf-8") as fh:
        fh.write(brief_md + "\n")

    return {
        "run_id": run_id,
        "inserted": inserted,
        "skipped": skipped,
        "themes": len(themes),
        "opportunities": len(opportunities),
        "rising": [t["label"] for t in themes if trend_by_theme[t["id"]]["rising"]],
        "brief_path": brief_path,
    }
