"""`bbsctl validate` — run the validator chain against a skill.

Phase 2 wires the fast validators (< 10 s):
  --fast (default)   enterprise-spec, basic-trigger, output-contract
  --full             fast + Phase 3 validators (not wired yet; same as --fast today)

Strictness is read from skill.yaml if present, then from project config
([tool.bulbasaur]), then defaults to LOCAL.

Exit codes: 0 = passed, 1 = validation errors, 2 = framework error.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import load_project_config
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness
from skillctl.validate import ValidateMode, ValidateResult, ValidateRunner


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "validate",
        help="Validate a skill at the current strictness level",
        description=(
            "Run the Bulbasaur validator chain. "
            "--fast (default) runs the team-tier sub-validators in < 10 s. "
            "--full adds Phase 3 validators (org strictness)."
        ),
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        default=True,
        help=(
            "Run fast sub-validators only (default). "
            "enterprise-spec, basic-trigger, output-contract."
        ),
    )
    p.add_argument(
        "--full",
        action="store_true",
        default=False,
        help=(
            "Run the full validator suite "
            "(Phase 3 adds registry-context trigger, injection corpus)."
        ),
    )
    p.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help="Override strictness (default: read from skill.yaml, then project config, then LOCAL)",
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json", "silent"],
        help="Output format (default: text)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()

    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing directory or `cd` into the skill directory first.",
            )
        )
        return 2

    strictness = _resolve_strictness(skill_dir, args.strictness)
    mode = ValidateMode.FULL if args.full else ValidateMode.FAST

    runner = ValidateRunner(skill_dir, strictness, mode=mode)
    result = runner.run()

    if args.output != "silent":
        _print_result(result, fmt=args.output)

    return 0 if result.passed else 1


def _resolve_strictness(skill_dir: Path, override: str | None) -> Strictness:
    """Resolution order: CLI override > skill.yaml > [tool.bulbasaur] > LOCAL."""
    if override:
        return Strictness.from_string(override)

    try:
        overlay = load_skill_yaml(skill_dir)
        if overlay is not None:
            return overlay.strictness
    except SkillYamlError:
        pass

    config = load_project_config(skill_dir)
    return config.default_strictness


def _print_result(result: ValidateResult, *, fmt: str) -> None:
    if fmt == "json":
        import json
        print(json.dumps(_result_to_dict(result), indent=2))
        return

    # Text output.
    mode_label = result.mode.value
    strictness_label = result.strictness.value
    status = "PASSED" if result.passed else "FAILED"

    info(f"validate [{mode_label}] @ {strictness_label}: {status}")
    info(f"  skill: {result.skill_dir}")
    info("")

    for r in result.results:
        icon = "✓" if r.passed else "✗"
        dur = f"{r.duration_ms}ms"
        info(f"  {icon} {r.validator_name} ({dur})")
        for err in r.errors:
            emit(err)
        for warn in r.warnings:
            # Warnings use the same emit() but are not fatal.
            info(f"    WARN: {warn.summary}")
            if warn.fix:
                info(f"      Fix: {warn.fix}")
        for note in r.notes:
            info(f"    note: {note}")

    info("")
    summary = f"  {result.total_errors} error(s), {result.total_warnings} warning(s)"
    if result.passed:
        info(f"Result: PASSED  {summary}")
    else:
        info(f"Result: FAILED  {summary}")


def _result_to_dict(result: ValidateResult) -> dict:
    return {
        "passed": result.passed,
        "mode": result.mode.value,
        "strictness": result.strictness.value,
        "skill_dir": str(result.skill_dir),
        "validators": [
            {
                "name": r.validator_name,
                "passed": r.passed,
                "duration_ms": r.duration_ms,
                "errors": [
                    {"summary": e.summary, "detail": e.detail, "fix": e.fix}
                    for e in r.errors
                ],
                "warnings": [
                    {"summary": w.summary, "fix": w.fix}
                    for w in r.warnings
                ],
                "notes": r.notes,
            }
            for r in result.results
        ],
    }


__all__ = ["register", "run"]
