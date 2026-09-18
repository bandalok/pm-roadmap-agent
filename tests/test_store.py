"""Tests for the SQLite store: dedupe, themes, triage, merge, scoring."""

from pm_roadmap_agent.store import content_hash, normalize_text


def test_add_feedback_and_dedupe(store, feedback_items):
    inserted, skipped = store.add_feedback(feedback_items)
    assert (inserted, skipped) == (4, 0)
    # Re-inserting the same items dedupes on content hash.
    inserted, skipped = store.add_feedback(feedback_items)
    assert (inserted, skipped) == (0, 4)
    assert store.feedback_count() == 4


def test_dedupe_is_case_and_whitespace_insensitive(store):
    store.add_feedback([{"source": "t", "text": "  The App CRASHED  "}])
    inserted, skipped = store.add_feedback([{"source": "t", "text": "the app crashed"}])
    assert (inserted, skipped) == (0, 1)


def test_empty_text_is_skipped(store):
    inserted, skipped = store.add_feedback(
        [{"source": "t", "text": "   "}, {"source": "t", "text": ""}]
    )
    assert (inserted, skipped) == (0, 2)


def test_normalize_and_hash():
    assert normalize_text("  Hello   WORLD ") == "hello world"
    assert content_hash("Hello") == content_hash("  hello ")


def _themes(store, feedback_items):
    store.add_feedback(feedback_items)
    run_id = store.create_run({"test": True})
    return run_id, store.save_themes(
        run_id,
        [
            {
                "label": "Crashes",
                "description": "App stability problems",
                "feedback_ids": ["fb_crash_1", "fb_crash_2"],
                "quotes": ["The app crashed twice during my commute"],
            },
            {
                "label": "Pricing",
                "description": "Price complaints",
                "feedback_ids": ["fb_price_1", "fb_price_2"],
                "quotes": [],
            },
        ],
    )


def test_save_and_list_themes(store, feedback_items):
    run_id, ids = _themes(store, feedback_items)
    assert len(ids) == 2
    themes = store.get_themes()
    assert {t["label"] for t in themes} == {"Crashes", "Pricing"}
    assert all(t["status"] == "pending" and t["run_id"] == run_id for t in themes)


def test_theme_feedback_links_and_quotes(store, feedback_items):
    _, ids = _themes(store, feedback_items)
    items = store.get_feedback_for_theme(ids[0])
    assert {i["id"] for i in items} == {"fb_crash_1", "fb_crash_2"}
    assert any(i["theme_quote"] for i in items)


def test_theme_stats(store, feedback_items):
    _, ids = _themes(store, feedback_items)
    stats = store.theme_stats(ids[0])
    assert stats["count"] == 2
    assert stats["avg_rating"] == 1.5


def test_set_theme_status(store, feedback_items):
    _, ids = _themes(store, feedback_items)
    store.set_theme_status(ids[0], "approved")
    assert store.get_theme(ids[0])["status"] == "approved"
    assert [t["id"] for t in store.get_themes(status="approved")] == [ids[0]]


def test_merge_themes_moves_evidence(store, feedback_items):
    _, ids = _themes(store, feedback_items)
    store.merge_themes(ids[0], ids[1])
    assert store.get_theme(ids[0])["status"] == "merged"
    assert store.get_theme(ids[0])["merged_into"] == ids[1]
    # Evidence consolidated onto the target.
    assert store.theme_stats(ids[1])["count"] == 4


def test_scores_and_ranked_opportunities(store, feedback_items):
    run_id, ids = _themes(store, feedback_items)
    store.save_scores(
        run_id,
        [
            {
                "theme_id": ids[0],
                "reach": 8,
                "impact": 9,
                "confidence": 7,
                "effort": 4,
                "rice": 126.0,
                "rationales": {},
            },
            {
                "theme_id": ids[1],
                "reach": 5,
                "impact": 4,
                "confidence": 6,
                "effort": 2,
                "rice": 60.0,
                "rationales": {},
            },
        ],
    )
    opps = store.get_opportunities(run_id=run_id)
    assert [o["label"] for o in opps] == ["Crashes", "Pricing"]
    assert opps[0]["rice"] == 126.0


def test_rejected_themes_excluded_from_opportunities(store, feedback_items):
    run_id, ids = _themes(store, feedback_items)
    store.set_theme_status(ids[0], "rejected")
    store.save_scores(
        run_id,
        [
            {
                "theme_id": tid,
                "reach": 5,
                "impact": 5,
                "confidence": 5,
                "effort": 5,
                "rice": 25.0,
                "rationales": {},
            }
            for tid in ids
        ],
    )
    opps = store.get_opportunities(run_id=run_id)
    assert [o["label"] for o in opps] == ["Pricing"]


def test_snapshots_upsert(store):
    store.save_snapshot("th_1", "2026-W36", 5)
    store.save_snapshot("th_1", "2026-W36", 9)  # upsert overwrites
    snaps = store.get_snapshots("th_1")
    assert snaps == [
        {"theme_id": "th_1", "week": "2026-W36", "feedback_count": 9}
    ]
