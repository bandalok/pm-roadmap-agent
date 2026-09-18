"""Streamlit UI — the human-in-the-loop console.

This is where the PM stays in charge of the agents:
  - Themes: review what the clusterer found; approve, reject, or merge.
    Triage decisions persist to SQLite and are respected downstream
    (rejected/merged themes never get scored).
  - Trends: per-week volume charts with rising themes flagged.
  - Opportunities: the RICE-ranked table with rationales.
  - Brief: the latest generated roadmap brief, rendered as Markdown.

Run with:
    streamlit run pm_roadmap_agent/ui/app.py
"""

from __future__ import annotations

import glob
import os

import pandas as pd
import streamlit as st

from pm_roadmap_agent.agents.trends import detect_rising
from pm_roadmap_agent.config import Config
from pm_roadmap_agent.store import Store


@st.cache_resource
def get_store(db_path: str) -> Store:
    return Store(db_path)


def latest_brief(briefs_dir: str) -> str | None:
    paths = sorted(glob.glob(os.path.join(briefs_dir, "roadmap-brief-*.md")))
    return paths[-1] if paths else None


def main() -> None:
    st.set_page_config(page_title="PM Roadmap Agent", layout="wide")
    config = Config()
    st.title("PM Roadmap Agent")
    st.caption("Feedback → themes → trends → RICE opportunities → roadmap brief")

    with st.sidebar:
        st.header("Data")
        st.text_input("Database path", value=config.db_path, key="db_path_display",
                      disabled=True)
        st.text_input("Briefs directory", value=config.briefs_dir, key="briefs_display",
                      disabled=True)
        if st.button("Refresh data"):
            st.rerun()

    store = get_store(config.db_path)
    themes = store.get_themes()
    opportunities = store.get_opportunities()

    col1, col2, col3 = st.columns(3)
    col1.metric("Feedback items", store.feedback_count())
    col2.metric("Themes", len(themes))
    col3.metric("Opportunities", len(opportunities))

    if not themes:
        st.info(
            "No themes yet. Run the pipeline first:\n\n"
            "`python -m pm_roadmap_agent --demo` (offline), or wire up "
            "ingestors and run `run_pipeline()` with an LLM provider."
        )
        return

    tab_themes, tab_trends, tab_opps, tab_brief = st.tabs(
        ["Themes", "Trends", "Opportunities", "Brief"]
    )

    # ---- Themes: human-in-the-loop triage --------------------------------
    with tab_themes:
        st.subheader("Theme triage")
        st.caption(
            "Approve themes worth pursuing, reject noise, merge duplicates. "
            "Rejected and merged themes are excluded from scoring."
        )
        for theme in themes:
            stats = store.theme_stats(theme["id"])
            with st.expander(
                f"[{theme['status']}] {theme['label']} — {stats['count']} items",
                expanded=theme["status"] == "pending",
            ):
                st.write(theme.get("description") or "")
                items = store.get_feedback_for_theme(theme["id"])
                quotes = [i["theme_quote"] for i in items if i.get("theme_quote")]
                for q in quotes[:2]:
                    st.markdown(f"> {q}")
                b1, b2, b3 = st.columns(3)
                if b1.button("Approve", key=f"approve-{theme['id']}"):
                    store.set_theme_status(theme["id"], "approved")
                    st.rerun()
                if b2.button("Reject", key=f"reject-{theme['id']}"):
                    store.set_theme_status(theme["id"], "rejected")
                    st.rerun()
                targets = [
                    t for t in themes
                    if t["id"] != theme["id"] and t["status"] not in ("merged", "rejected")
                ]
                if targets:
                    target = b3.selectbox(
                        "Merge into",
                        options=[t["id"] for t in targets],
                        format_func=lambda tid: next(
                            t["label"] for t in targets if t["id"] == tid
                        ),
                        key=f"merge-{theme['id']}",
                    )
                    if b3.button("Merge", key=f"merge-btn-{theme['id']}"):
                        store.merge_themes(theme["id"], target)
                        st.rerun()

    # ---- Trends -----------------------------------------------------------
    with tab_trends:
        st.subheader("Theme volume by week")
        frames = {}
        rising_labels = []
        for theme in themes:
            snaps = store.get_snapshots(theme["id"])
            if not snaps:
                continue
            series = pd.Series(
                {s["week"]: s["feedback_count"] for s in snaps},
                name=theme["label"],
            )
            frames[theme["label"]] = series
            history = {s["week"]: s["feedback_count"] for s in snaps}
            rising, _ = detect_rising(
                history,
                min_count=config.trend_min_count,
                growth_factor=config.trend_growth_factor,
            )
            if rising:
                rising_labels.append(theme["label"])
        if frames:
            df = pd.DataFrame(frames).fillna(0).astype(int).sort_index()
            st.line_chart(df)
            if rising_labels:
                st.warning("Rising: " + ", ".join(rising_labels))
            else:
                st.success("No spikes — volume is stable across themes.")
        else:
            st.info("No trend history yet — run the pipeline to record snapshots.")

    # ---- Opportunities ----------------------------------------------------
    with tab_opps:
        st.subheader("Ranked opportunities (RICE)")
        if opportunities:
            df = pd.DataFrame(
                [
                    {
                        "Opportunity": o["label"],
                        "RICE": round(o["rice"], 1),
                        "Reach": o["reach"],
                        "Impact": o["impact"],
                        "Confidence": o["confidence"],
                        "Effort": o["effort"],
                        "Feedback": o["feedback_count"],
                        "Status": o["status"],
                    }
                    for o in opportunities
                ]
            )
            st.dataframe(df, width="stretch", hide_index=True)
            for opp in opportunities:
                with st.expander(f"Why: {opp['label']}"):
                    import json as _json

                    rationales = _json.loads(opp["rationale"] or "{}")
                    for key in ("reach", "impact", "confidence", "effort"):
                        st.write(f"**{key.capitalize()} ({opp[key]}/10):** "
                                 f"{rationales.get(key, '—')}")
        else:
            st.info("No scored opportunities yet.")

    # ---- Brief ------------------------------------------------------------
    with tab_brief:
        st.subheader("Latest roadmap brief")
        path = latest_brief(config.briefs_dir)
        if path:
            st.caption(path)
            with open(path, encoding="utf-8") as fh:
                st.markdown(fh.read())
        else:
            st.info("No brief generated yet.")


if __name__ == "__main__":
    main()
