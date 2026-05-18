"""`skillctl compile` — compile the skill at PWD (or --dir).

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
from skillctl.strictness import Strictness


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
        choices=[s.value for s in Strictness],
        help="Override strictness for this compile (default: read from skill.yaml or LOCAL)",
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json", "silent"],
        help="Output format (default: text)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute `skillctl compile`."""
    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.exists() or not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix=(
                    "Pass an existing directory, or `cd` into the skill directory "
                    "before running `skillctl compile`."
                ),
            )
        )
        return 1

    strictness = _resolve_strictness(skill_dir, args.strictness)
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
    """Resolve strictness from (in order): CLI override, skill.yaml, default LOCAL.

    Phase 1 does not implement skill.yaml reading (it lands in Phase 2 with the
    enterprise overlay). For now the override or LOCAL is the only source.
    """
    if override:
        return Strictness.from_string(override)

    # Phase 2: read skill_dir/skill.yaml for the `strictness:` key.
    return Strictness.LOCAL


__all__ = ["register", "run"]
