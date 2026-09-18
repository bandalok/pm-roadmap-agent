"""Weekly digest — regenerate the brief and deliver a summary.

Default behavior prints the digest to stdout (safe everywhere, including
cron). With ``--email`` and SMTP configured via environment (see
.env.example), it also emails the brief to DIGEST_TO.

Typical cron usage (Monday 9am):
    0 9 * * MON cd /path/to/pm-roadmap-agent && python -m pm_roadmap_agent.digest --refresh
"""

from __future__ import annotations

import argparse
import os
import smtplib
from email.message import EmailMessage

from .config import Config
from .pipeline import run_pipeline
from .store import Store


def render_digest(store: Store, run_id: str | None = None) -> str:
    """Render a plain-text digest from the latest (or given) run."""
    opportunities = store.get_opportunities(run_id=run_id)
    themes = store.get_themes()
    lines = [
        "PM ROADMAP AGENT — WEEKLY DIGEST",
        f"Feedback in database: {store.feedback_count()}",
        f"Themes tracked: {len(themes)}",
        "",
        "TOP OPPORTUNITIES (RICE)",
    ]
    for i, opp in enumerate(opportunities[:5], 1):
        lines.append(
            f"{i}. {opp['label']} — RICE {opp['rice']:.1f} "
            f"(R{opp['reach']} I{opp['impact']} C{opp['confidence']} E{opp['effort']}, "
            f"n={opp['feedback_count']})"
        )
    if not opportunities:
        lines.append("(no scored opportunities yet — run the pipeline first)")
    lines += ["", "THEME STATUS"]
    for theme in themes:
        count_row = store.theme_stats(theme["id"])
        lines.append(
            f"- [{theme['status']}] {theme['label']} ({count_row['count']} items)"
        )
    return "\n".join(lines)


def send_email(config: Config, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.digest_from or config.smtp_user
    msg["To"] = config.digest_to
    msg.set_content(body)
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate and deliver the weekly digest.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run the pipeline before rendering (uses configured ingestors).",
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help="Email the digest (requires SMTP_* env vars).",
    )
    parser.add_argument(
        "--heuristic",
        action="store_true",
        help="Use the offline heuristic path (no LLM key needed).",
    )
    args = parser.parse_args(argv)

    config = Config()
    store = Store(config.db_path)
    try:
        run_id = None
        if args.refresh:
            # NOTE: refresh reuses whatever ingestors the deployer wires in.
            # For a first run, ingest via the demo or the UI instead.
            summary = run_pipeline(config, ingestors=[], use_heuristics=args.heuristic, store=store)
            run_id = summary["run_id"]
            print(f"Pipeline refreshed: {summary['themes']} themes, "
                  f"brief at {summary['brief_path']}")
        digest = render_digest(store, run_id=run_id)
        print()
        print(digest)
        if args.email:
            if not config.smtp_configured:
                print("\nSMTP not configured; skipping email. See .env.example.")
                return 1
            send_email(config, "Weekly roadmap digest", digest)
            print(f"\nDigest emailed to {config.digest_to}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
