"""`bbsctl compile` — compile the skill at PWD (or --dir).

Phase 1 wires the compile pipeline (see skillctl/compile/) at the configured
strictness and exits with the appropriate code. Later phases add `--repair`
(Mellea-style), `--fast`, and additional steps registered through the factory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.compile import (
    CompileContext,
    JsonReporter,
    NullReporter,
    Reporter,
    TextReporter,
    build_pipeline,
)
from skillctl.messaging import FrameworkError, emit
from skillctl.project_config import load_project_config
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness, fail_if_unsupported, register_support, supported_levels

# Phase 2: `team` strictness is now supported for compile.
register_support("compile", Strictness.TEAM)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Wire the `compile` subcommand into the CLI."""
    p = subparsers.add_parser(
        "compile",
        help="Compile the skill in the current directory",
        description="Run the compile pipeline against a skill, emitting dist/compile-report.json.",
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    p.add_argument(
        "--strictness",
        default=None,
        choices=supported_levels("compile"),
        help="Override strictness for this compile (default: read from skill.yaml or LOCAL).",
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json", "silent"],
        help="Output format (default: text)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute `bbsctl compile`."""
    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.exists() or not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix=(
                    "Pass an existing directory, or `cd` into the skill directory "
                    "before running `bbsctl compile`."
                ),
            )
        )
        return 1

    strictness = _resolve_strictness(skill_dir, args.strictness)

    # Vapor-options guard for programmatic invocations that bypass argparse choices.
    unsupported_fix = fail_if_unsupported("compile", strictness)
    if unsupported_fix is not None:
        emit(
            FrameworkError(
                summary=f"strictness `{strictness.value}` is not supported by `bbsctl compile` yet",
                detail="vapor-options guard (see docs/audits/phase-1.md F3)",
                fix=unsupported_fix,
                docs="../docs/strictness-levels.md",
            )
        )
        return 1

    reporter: Reporter = _build_reporter(args.output)

    reporter.on_start(skill_dir=str(skill_dir), strictness=strictness.value)

    pipeline = build_pipeline(strictness=strictness)
    context = CompileContext(
        skill_dir=skill_dir,
        strictness=strictness,
        reporter=reporter,
    )
    result = pipeline.run(context)

    return 0 if result.success else 1


def _build_reporter(output: str) -> Reporter:
    """Strategy factory for reporters."""
    if output == "json":
        return JsonReporter()
    if output == "silent":
        return NullReporter()
    return TextReporter()


def _resolve_strictness(skill_dir: Path, override: str | None) -> Strictness:
    """Resolve strictness: CLI override > skill.yaml > [tool.bulbasaur] > LOCAL."""
    if override:
        return Strictness.from_string(override)

    try:
        overlay = load_skill_yaml(skill_dir)
        if overlay is not None:
            return overlay.strictness
    except SkillYamlError:
        pass  # parse error reported elsewhere; fall through to default

    config = load_project_config(skill_dir)
    return config.default_strictness


__all__ = ["register", "run"]
