"""Package CLI.

    python -m pm_roadmap_agent --demo      # one-command offline demo
    python -m pm_roadmap_agent.demo       # same, as a module
    python -m pm_roadmap_agent.digest     # weekly digest
"""

from __future__ import annotations

import argparse
import sys

from .demo import main as demo_main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pm-roadmap-agent")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the offline demo pipeline (no API key needed).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="With --demo: keep outputs under ./demo-output.",
    )
    args = parser.parse_args(argv)
    if args.demo:
        return demo_main(["--keep"] if args.keep else [])
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
