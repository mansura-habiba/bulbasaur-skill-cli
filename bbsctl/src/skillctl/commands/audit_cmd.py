"""`bbsctl audit <path>` — trust evaluation for a downloaded skill.

Before you install or activate a skill from an external source, run
`bbsctl audit` to generate a trust report. The report checks:

    spec-completeness    Are required fields present and filled in?
    body-sections        Does the body have Instructions, Guardrails, etc.?
    guardrails-quality   Are the guardrails concrete or just placeholders?
    scripts              Does the skill include executable code?
    allowed-tools        Does it request broad tool permissions?
    enterprise-overlay   Is there ownership, strictness, signing?

The verdict is one of:
    TRUSTED              All checks pass or have only informational notes
    REVIEW               Warnings present — review before trusting
    DO NOT TRUST         Risk or failure-level issues found
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.audit.runner import AuditRunner
from skillctl.messaging import FrameworkError, emit, info


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "audit",
        help="Evaluate trust of a downloaded skill",
        description=(
            "Run trust checks on a skill directory and generate a report. "
            "Use before installing or activating third-party skills."
        ),
    )
    p.add_argument(
        "path",
        help="Path to the skill directory to audit",
    )
    p.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    skill_dir = Path(args.path).resolve()

    if not skill_dir.exists():
        emit(FrameworkError(
            summary=f"path not found: {skill_dir}",
            fix="Pass the path to a skill directory containing SKILL.md.",
        ))
        return 1

    if not skill_dir.is_dir():
        emit(FrameworkError(
            summary=f"not a directory: {skill_dir}",
            fix="Pass the path to a skill directory, not a file.",
        ))
        return 1

    runner = AuditRunner(skill_dir)
    report = runner.run()

    if args.output == "json":
        print(report.format_json())
    else:
        verdict = report.verdict
        worst = report.worst_severity.name
        info(f"audit: {verdict}  (worst: {worst})")
        info(report.format_text())

        if report.worst_severity.value >= 3:
            info("Action required before trusting this skill:")
            risks = [
                f for f in report.all_findings
                if f.severity.value >= 3
            ]
            for f in risks:
                info(f"  • {f.title}")
                if f.recommendation:
                    info(f"    → {f.recommendation}")

    return 0 if report.worst_severity.value < 4 else 1


__all__ = ["register", "run"]
