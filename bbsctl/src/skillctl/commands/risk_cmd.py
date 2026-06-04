"""`bbsctl risk` — inspect the (strictness × risk_level) matrix.

Three subcommands:

  bbsctl risk show                     # print the full 16-cell matrix
  bbsctl risk cell <strict> <risk>     # print one cell's controls
  bbsctl risk check [skill_dir]        # run RiskMatrixValidator against a skill

The matrix is shipped as data in `skillctl.risk_matrix`; this is the
operator-facing surface for that data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.risk_matrix import (
    DEFAULT_RISK_MATRIX,
    get_matrix_cell,
    render_matrix,
)
from skillctl.skill_yaml import RiskLevel
from skillctl.strictness import Strictness
from skillctl.validate.risk_matrix_validator import RiskMatrixValidator


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "risk",
        help="Inspect the (strictness × risk_level) control matrix.",
        description=(
            "The framework's default matrix declares, for every (strictness, "
            "risk_level) pair, which controls are required (injection corpus, "
            "human approval, signed bundle, sandbox, security reviewer, max "
            "side effects). `bbsctl risk` lets a reviewer see the matrix and "
            "check a skill against it."
        ),
    )
    sub = p.add_subparsers(dest="risk_command", metavar="<subcommand>")

    # ── show ─────────────────────────────────────────────────────────────
    show_p = sub.add_parser(
        "show",
        help="Print the full 16-cell matrix.",
    )
    show_p.add_argument(
        "--output",
        default="text",
        choices=["text", "json"],
        help="Output format (default: text).",
    )
    show_p.set_defaults(func=_run_show)

    # ── cell ─────────────────────────────────────────────────────────────
    cell_p = sub.add_parser(
        "cell",
        help="Print one cell's controls.",
    )
    cell_p.add_argument(
        "strictness",
        choices=[s.value for s in Strictness],
        help="Strictness rung.",
    )
    cell_p.add_argument(
        "risk_level",
        choices=[r.value for r in RiskLevel],
        help="Risk level.",
    )
    cell_p.add_argument(
        "--output",
        default="text",
        choices=["text", "json"],
        help="Output format (default: text).",
    )
    cell_p.set_defaults(func=_run_cell)

    # ── check ────────────────────────────────────────────────────────────
    check_p = sub.add_parser(
        "check",
        help="Run RiskMatrixValidator against a skill.",
    )
    check_p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory).",
    )
    check_p.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help="Override strictness (default: read from skill.yaml).",
    )
    check_p.add_argument(
        "--output",
        default="text",
        choices=["text", "json"],
        help="Output format (default: text).",
    )
    check_p.set_defaults(func=_run_check)

    p.set_defaults(func=_no_subcommand(p))


def _no_subcommand(parser: argparse.ArgumentParser):
    def _run(args: argparse.Namespace) -> int:
        parser.print_help()
        return 0

    return _run


# ── show ────────────────────────────────────────────────────────────────────


def _run_show(args: argparse.Namespace) -> int:
    rows = render_matrix()
    if args.output == "json":
        payload = [
            {
                "strictness": r.strictness,
                "risk_level": r.risk_level,
                "allowed": r.allowed,
                "controls": list(r.controls),
                "rationale": r.rationale,
            }
            for r in rows
        ]
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    info(f"{'strictness':<11}  {'risk':<10}  {'ok':<3}  controls")
    info("-" * 80)
    for r in rows:
        ok = "Y" if r.allowed else "N"
        controls = ", ".join(r.controls) if r.controls else "(none)"
        info(f"{r.strictness:<11}  {r.risk_level:<10}  {ok:<3}  {controls}")
        if r.rationale:
            info(f"{'':<11}  {'':<10}  {'':<3}  → {r.rationale}")
    return 0


# ── cell ────────────────────────────────────────────────────────────────────


def _run_cell(args: argparse.Namespace) -> int:
    strictness = Strictness.from_string(args.strictness)
    risk = RiskLevel.from_string(args.risk_level)
    if risk is None:
        emit(
            FrameworkError(
                summary=f"unknown risk level: {args.risk_level!r}",
                fix=f"Pick one of: {', '.join(r.value for r in RiskLevel)}.",
            )
        )
        return 2
    cell = get_matrix_cell(strictness, risk)

    if args.output == "json":
        sys.stdout.write(
            json.dumps(
                {
                    "strictness": cell.strictness,
                    "risk_level": cell.risk_level,
                    "allowed": cell.allowed,
                    "rationale": cell.rationale,
                    "controls": {
                        "require_injection_corpus": cell.require_injection_corpus,
                        "require_human_approval": cell.require_human_approval,
                        "require_signed_bundle": cell.require_signed_bundle,
                        "require_sandbox": cell.require_sandbox,
                        "require_security_reviewer": cell.require_security_reviewer,
                        "max_side_effects": cell.max_side_effects,
                    },
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    info(f"Cell ({cell.strictness}, {cell.risk_level})")
    info("=" * 50)
    info(f"  allowed:                     {cell.allowed}")
    info(f"  rationale:                   {cell.rationale or '(none)'}")
    info("")
    info("  Required controls:")
    info(f"    injection_corpus:          {cell.require_injection_corpus}")
    info(f"    human_approval:            {cell.require_human_approval}")
    info(f"    signed_bundle:             {cell.require_signed_bundle}")
    info(f"    sandbox:                   {cell.require_sandbox}")
    info(f"    security_reviewer:         {cell.require_security_reviewer}")
    info(
        f"    max_side_effects:          {cell.max_side_effects or '(unset)'}"
    )
    return 0


# ── check ──────────────────────────────────────────────────────────────────


def _run_check(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing directory or `cd` into the skill first.",
            )
        )
        return 2

    strictness = _resolve_strictness(skill_dir, args.strictness)
    result = RiskMatrixValidator().run(skill_dir, strictness)

    if args.output == "json":
        sys.stdout.write(
            json.dumps(
                {
                    "passed": result.passed,
                    "strictness": strictness.value,
                    "skill_dir": str(skill_dir),
                    "errors": [
                        {"summary": e.summary, "detail": e.detail, "fix": e.fix}
                        for e in result.errors
                    ],
                    "warnings": [
                        {"summary": w.summary, "detail": w.detail}
                        for w in result.warnings
                    ],
                    "notes": list(result.notes),
                },
                indent=2,
            )
            + "\n"
        )
        return 0 if result.passed else 1

    status = "PASSED" if result.passed else "FAILED"
    info(f"risk-matrix @ {strictness.value}: {status}")
    info(f"  skill: {skill_dir}")
    info("")
    for note in result.notes:
        info(f"  · {note}")
    for w in result.warnings:
        info(f"  WARN: {w.summary}")
        if w.detail:
            info(f"        detail: {w.detail}")
    for e in result.errors:
        info(f"  ERROR: {e.summary}")
        if e.detail:
            info(f"         detail: {e.detail}")
        if e.fix:
            info(f"         Fix: {e.fix}")
    return 0 if result.passed else 1


def _resolve_strictness(skill_dir: Path, override: str | None) -> Strictness:
    """Resolution order: CLI override > skill.yaml > LOCAL."""
    if override:
        return Strictness.from_string(override)
    from skillctl.skill_yaml import SkillYamlError, load_skill_yaml

    try:
        overlay = load_skill_yaml(skill_dir)
    except SkillYamlError:
        return Strictness.LOCAL
    return overlay.strictness if overlay else Strictness.LOCAL


__all__ = ["register"]
