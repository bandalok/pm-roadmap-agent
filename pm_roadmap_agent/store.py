"""SQLite persistence for the feedback-to-roadmap pipeline.

Schema rationale (why these tables and not a document blob):
- ``feedback`` is append-only raw evidence. Dedupe is enforced on a content
  hash so re-running ingestion is idempotent — a PM re-running the pipeline
  should never double-count a review.
- ``themes`` are the PM's working set, with a human-in-the-loop ``status``
  (pending / approved / rejected / merged) rather than a boolean, because
  triage is a workflow, not a flag.
- ``theme_feedback`` links themes to their evidence with a stored
  representative ``quote``, so the UI and brief can show proof without
  re-querying.
- ``theme_snapshots`` records per-week theme volume so trends are computed
  from history, not recomputed from scratch each run.
- ``scores`` holds one RICE assessment per theme per run; keeping run
  history lets a PM see how prioritization evolved.
- ``runs`` ties a full pipeline execution together for auditability.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    """Canonical form used for dedupe: lowercase, collapsed whitespace."""
    return " ".join(text.lower().split())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT,
    text TEXT NOT NULL,
    author TEXT,
    rating REAL,
    created_at TEXT,
    language TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS themes (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    merged_into TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS theme_feedback (
    theme_id TEXT NOT NULL,
    feedback_id TEXT NOT NULL,
    quote TEXT,
    PRIMARY KEY (theme_id, feedback_id)
);
CREATE TABLE IF NOT EXISTS theme_snapshots (
    theme_id TEXT NOT NULL,
    week TEXT NOT NULL,
    feedback_count INTEGER NOT NULL,
    PRIMARY KEY (theme_id, week)
);
CREATE TABLE IF NOT EXISTS scores (
    theme_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    reach INTEGER NOT NULL,
    impact INTEGER NOT NULL,
    confidence INTEGER NOT NULL,
    effort INTEGER NOT NULL,
    rice REAL NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (theme_id, run_id)
);
"""


class Store:
    """Thin, explicit data-access layer over SQLite."""

    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # -- feedback ------------------------------------------------------
    def add_feedback(self, items: list[dict]) -> tuple[int, int]:
        """Insert feedback items, skipping exact-content duplicates.

        Returns (inserted, skipped).
        """
        inserted = skipped = 0
        now = _utcnow()
        for item in items:
            text = (item.get("text") or "").strip()
            if not text:
                skipped += 1
                continue
            digest = content_hash(text)
            try:
                self._conn.execute(
                    """INSERT INTO feedback
                       (id, source, source_id, text, author, rating, created_at,
                        language, content_hash, ingested_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.get("id") or f"fb_{uuid.uuid4().hex[:12]}",
                        item.get("source", "unknown"),
                        item.get("source_id"),
                        text,
                        item.get("author"),
                        item.get("rating"),
                        item.get("created_at"),
                        item.get("language"),
                        digest,
                        now,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1  # duplicate content hash (or id collision)
        self._conn.commit()
        return inserted, skipped

    def feedback_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()
        return row["n"]

    def get_feedback(self, limit: int | None = None) -> list[dict]:
        sql = "SELECT * FROM feedback ORDER BY created_at NULLS LAST, id"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self._conn.execute(sql).fetchall()]

    # -- runs ----------------------------------------------------------
    def create_run(self, config: dict) -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            "INSERT INTO runs (id, started_at, config_json) VALUES (?, ?, ?)",
            (run_id, _utcnow(), json.dumps(config)),
        )
        self._conn.commit()
        return run_id

    # -- themes --------------------------------------------------------
    def save_themes(self, run_id: str, themes: list[dict]) -> list[str]:
        """Persist clustered themes; returns their ids in order."""
        ids = []
        now = _utcnow()
        for theme in themes:
            theme_id = theme.get("id") or f"th_{uuid.uuid4().hex[:12]}"
            self._conn.execute(
                """INSERT INTO themes (id, run_id, label, description, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (theme_id, run_id, theme["label"], theme.get("description", ""), now),
            )
            for fid in theme.get("feedback_ids", []):
                self._conn.execute(
                    "INSERT OR IGNORE INTO theme_feedback (theme_id, feedback_id) VALUES (?, ?)",
                    (theme_id, fid),
                )
            for quote in theme.get("quotes", [])[:2]:
                # Attach quotes to linked rows that lack one yet.
                self._conn.execute(
                    """UPDATE theme_feedback SET quote = ?
                       WHERE theme_id = ? AND quote IS NULL
                       LIMIT 1""",
                    (quote, theme_id),
                )
            ids.append(theme_id)
        self._conn.commit()
        return ids

    def get_themes(self, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM themes"
        params: tuple = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY created_at"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def get_theme(self, theme_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM themes WHERE id = ?", (theme_id,)
        ).fetchone()
        return dict(row) if row else None

    def set_theme_status(
        self, theme_id: str, status: str, merged_into: str | None = None
    ) -> None:
        if status not in ("pending", "approved", "rejected", "merged"):
            raise ValueError(f"Unknown theme status: {status!r}")
        self._conn.execute(
            "UPDATE themes SET status = ?, merged_into = ? WHERE id = ?",
            (status, merged_into, theme_id),
        )
        self._conn.commit()

    def get_feedback_for_theme(self, theme_id: str) -> list[dict]:
        return [
            dict(r)
            for r in self._conn.execute(
                """SELECT f.*, tf.quote AS theme_quote FROM feedback f
                   JOIN theme_feedback tf ON tf.feedback_id = f.id
                   WHERE tf.theme_id = ? ORDER BY f.created_at NULLS LAST""",
                (theme_id,),
            ).fetchall()
        ]

    def theme_stats(self, theme_id: str) -> dict:
        """Volume + rating evidence for one theme (feeds scoring)."""
        rows = self.get_feedback_for_theme(theme_id)
        ratings = [r["rating"] for r in rows if r["rating"] is not None]
        return {
            "count": len(rows),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        }

    # -- snapshots (trends) --------------------------------------------
    def save_snapshot(self, theme_id: str, week: str, count: int) -> None:
        self._conn.execute(
            """INSERT INTO theme_snapshots (theme_id, week, feedback_count)
               VALUES (?, ?, ?)
               ON CONFLICT(theme_id, week) DO UPDATE SET feedback_count = excluded.feedback_count""",
            (theme_id, week, count),
        )
        self._conn.commit()

    def get_snapshots(self, theme_id: str) -> list[dict]:
        return [
            dict(r)
            for r in self._conn.execute(
                "SELECT * FROM theme_snapshots WHERE theme_id = ? ORDER BY week",
                (theme_id,),
            ).fetchall()
        ]

    # -- scores --------------------------------------------------------
    def save_scores(self, run_id: str, scores: list[dict]) -> None:
        now = _utcnow()
        for s in scores:
            self._conn.execute(
                """INSERT INTO scores
                   (theme_id, run_id, reach, impact, confidence, effort, rice, rationale, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(theme_id, run_id) DO UPDATE SET
                     reach = excluded.reach, impact = excluded.impact,
                     confidence = excluded.confidence, effort = excluded.effort,
                     rice = excluded.rice, rationale = excluded.rationale""",
                (
                    s["theme_id"],
                    run_id,
                    s["reach"],
                    s["impact"],
                    s["confidence"],
                    s["effort"],
                    s["rice"],
                    json.dumps(s.get("rationales", {})),
                    now,
                ),
            )
        self._conn.commit()

    def get_opportunities(self, run_id: str | None = None) -> list[dict]:
        """Ranked opportunities: themes joined with their latest RICE scores.

        Rejected themes are excluded — a PM's triage decision is respected
        downstream. Merged themes are excluded in favor of their target.
        With no run_id, the latest run's scores are used (one row per theme).
        """
        if run_id is None:
            row = self._conn.execute(
                "SELECT id FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            run_id = row["id"] if row else None
        sql = """
            SELECT t.id, t.label, t.description, t.status,
                   s.reach, s.impact, s.confidence, s.effort, s.rice, s.rationale,
                   (SELECT COUNT(*) FROM theme_feedback tf WHERE tf.theme_id = t.id) AS feedback_count
            FROM themes t
            JOIN scores s ON s.theme_id = t.id
            WHERE t.status != 'rejected' AND t.status != 'merged'
              AND s.run_id = ?
        """
        params: tuple = (run_id,)
        sql += " ORDER BY s.rice DESC"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def merge_themes(self, source_id: str, target_id: str) -> None:
        """Merge ``source_id`` into ``target_id`` (human-in-the-loop triage).

        Evidence (feedback links + quotes) moves to the target so the
        surviving theme keeps the full picture; the source is marked
        ``merged`` and excluded from future scoring. Snapshots stay with
        their original theme id so history is never rewritten.
        """
        if source_id == target_id:
            raise ValueError("Cannot merge a theme into itself.")
        if not self.get_theme(source_id) or not self.get_theme(target_id):
            raise ValueError("Unknown theme id in merge.")
        # Move evidence links to the target (keep existing quotes).
        self._conn.execute(
            """INSERT OR IGNORE INTO theme_feedback (theme_id, feedback_id, quote)
               SELECT ?, feedback_id, quote FROM theme_feedback WHERE theme_id = ?""",
            (target_id, source_id),
        )
        self._conn.execute(
            "DELETE FROM theme_feedback WHERE theme_id = ?", (source_id,)
        )
        self.set_theme_status(source_id, "merged", merged_into=target_id)

    def close(self) -> None:
        self._conn.close()
