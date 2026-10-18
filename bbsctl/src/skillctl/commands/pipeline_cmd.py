"""`bbsctl pipeline` — walk lifecycle stages, fail fast.

The CLI binary stays `bbsctl`. lifecycle is the internal orchestrator package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import load_project_config
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.lifecycle.config import load_lifecycle_config
from skillctl.lifecycle.engines import build_engines
from skillctl.lifecycle.evidence import assemble_evidence
from skillctl.lifecycle.pipeline import (
    Runner,
    Stage,
    plan_for_strictness,
    resume_fix,
)
from skillctl.lifecycle.result import StageStatus
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "pipeline",
        help="Run the lifecycle (compile → scan → eval → …), fail fast",
        description=(
            "Walk the stages required for the skill's strictness. "
            "Delegates each stage to a configured engine. "
            "Exit: 0=ok, 1=stage failed, 2=engine/framework error, 3=waiting on approve."
        ),
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
        help="Override strictness (default: skill.yaml / project / bbsctl config)",
    )
    p.add_argument(
        "--from",
        dest="from_stage",
        default=None,
        choices=[s.value for s in Stage if s != Stage.NEW],
        help="Start at this stage (inclusive)",
    )
    p.add_argument(
        "--to",
        dest="to_stage",
        default=None,
        choices=[s.value for s in Stage if s != Stage.NEW],
        help="Stop after this stage (inclusive)",
    )
    p.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="STAGE",
        choices=[s.value for s in Stage if s != Stage.NEW],
        help="Skip an optional stage (repeatable; refused for required stages)",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        default=False,
        help="Pre-commit path: compile + validate --fast only (implies --to compile)",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable the stage cache",
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json"],
        help="Output format (default: text)",
    )
    p.add_argument(
        "--marketplace",
        default=None,
        help="Marketplace path when the publish stage runs",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing skill directory, or `cd` into one first.",
            )
        )
        return 2

    config = load_lifecycle_config(skill_dir)
    strictness = _resolve_strictness(skill_dir, args.strictness, config.default_strictness)
    plan = plan_for_strictness(strictness)

    from_stage = Stage(args.from_stage) if args.from_stage else None
    to_stage = Stage.COMPILE if args.fast else (
        Stage(args.to_stage) if args.to_stage else None
    )
    skip = {Stage(s) for s in (args.skip or [])}

    runner = Runner(
        skill_dir=skill_dir,
        config=config,
        engines=build_engines(config),
        use_cache=not args.no_cache,
        fast=bool(args.fast),
        marketplace=args.marketplace,
    )
    report = runner.run(
        plan,
        from_stage=from_stage,
        to_stage=to_stage,
        skip=skip,
    )

    if report.results:
        try:
            assemble_evidence(skill_dir, results=report.results, strictness=strictness)
        except OSError:
            pass

    if args.output == "json":
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        for r in report.results:
            tag = r.status.value.upper()
            cached = " (cached)" if r.cached else ""
            info(f"  [{tag}] {r.stage}  engine={r.engine.name}{cached}  {r.detail}")
            for f in r.findings[:5]:
                info(f"         · [{f.severity}] {f.message}")

    if report.exit_code == 2:
        failed = next(
            (
                r
                for r in reversed(report.results)
                if r.status == StageStatus.ERROR
            ),
            None,
        )
        if failed is not None:
            emit(
                FrameworkError(
                    summary=f"pipeline stopped: engine error at `{failed.stage}`",
                    detail=failed.detail or "engine/framework error",
                    fix=resume_fix(failed.stage, skill_dir=skill_dir),
                    docs="../docs/recipes/how-to-run-pipeline.md",
                )
            )

    return report.exit_code


def _resolve_strictness(
    skill_dir: Path, override: str | None, lifecycle_default: Strictness
) -> Strictness:
    if override:
        return Strictness.from_string(override)
    try:
        overlay = load_skill_yaml(skill_dir)
        if overlay is not None:
            return overlay.strictness
    except SkillYamlError:
        pass
    project = load_project_config(skill_dir)
    if project.default_strictness != Strictness.LOCAL:
        return project.default_strictness
    return lifecycle_default


__all__ = ["register", "run"]
