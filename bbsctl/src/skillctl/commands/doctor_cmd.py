"""`bbsctl doctor` — report lifecycle engine availability and pin match."""

from __future__ import annotations

import argparse
import json
import sys

from skillctl.lifecycle.doctor import check_engines, format_doctor_report


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "doctor",
        help="Check lifecycle engines (bbsctl / SkillSpector / Mellea)",
        description=(
            "Report which engines are on PATH, their versions, and whether "
            "they match the pinned SHAs in [tool.uv.sources]."
        ),
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json"],
        help="Output format (default: text)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    rows = check_engines()
    if args.output == "json":
        sys.stdout.write(json.dumps([r.to_dict() for r in rows], indent=2) + "\n")
    else:
        sys.stdout.write(format_doctor_report(rows))
    # Non-zero only if bbsctl itself is missing (should never happen).
    return 0 if any(r.name == "bbsctl" and r.found for r in rows) else 2


__all__ = ["register", "run"]
