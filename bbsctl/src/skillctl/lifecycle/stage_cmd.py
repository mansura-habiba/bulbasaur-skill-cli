"""Shared helpers for single-stage bbsctl commands (scan, certify, …)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import load_project_config
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.lifecycle.config import LifecycleConfig, load_lifecycle_config
from skillctl.lifecycle.engines import build_engines
from skillctl.lifecycle.engines.base import Engine, StageContext
from skillctl.lifecycle.evidence import assemble_evidence
from skillctl.lifecycle.pipeline import Stage, resume_fix
from skillctl.lifecycle.result import StageResult, StageStatus
from skillctl.strictness import Strictness


def add_stage_command_args(
    parser: argparse.ArgumentParser,
    *,
    strictness_help: str = "Override strictness",
) -> None:
    """Common CLI flags shared by inspect / scan / certify / mellea-certify."""
    parser.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    parser.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help=strictness_help,
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable the stage cache",
    )
    parser.add_argument(
        "--output",
        default="text",
        choices=["text", "json"],
        help="Output format (default: text)",
    )


def resolve_strictness(
    skill_dir: Path, override: str | None, config: LifecycleConfig
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
    return config.default_strictness


def run_single_stage(
    *,
    skill_dir: Path,
    stage: Stage,
    strictness_override: str | None,
    output: str = "text",
    use_cache: bool = True,
    marketplace: str | None = None,
    approve_by: str | None = None,
    approve_note: str = "",
    engine_override: Engine | None = None,
    resume_command: str | None = None,
) -> int:
    """Run one lifecycle stage via its configured (or overridden) engine."""
    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing skill directory, or `cd` into one first.",
            )
        )
        return 2

    config = load_lifecycle_config(skill_dir)
    strictness = resolve_strictness(skill_dir, strictness_override, config)
    if engine_override is not None:
        engine = engine_override
    else:
        engines = build_engines(config)
        engine = engines.get(stage)
    if engine is None:
        emit(
            FrameworkError(
                summary=f"no engine registered for stage `{stage.value}`",
                fix="Check `[tool.bbsctl.engines]` in pyproject.toml.",
                docs="../docs/lifecycle.md",
            )
        )
        return 2

    resume_hint = (
        f"After fixing the engine, re-run: `bbsctl {resume_command}`."
        if resume_command
        else resume_fix(stage, skill_dir=skill_dir)
    )

    if not engine.available():
        emit(
            FrameworkError(
                summary=f"engine `{engine.name}` not available for stage `{stage.value}`",
                detail=f"strictness={strictness.value}",
                fix=f"{engine.install_fix()}\n{resume_hint}",
                docs="../docs/recipes/how-to-commands.md",
            )
        )
        return 2

    ctx = StageContext(
        skill_dir=skill_dir,
        stage=stage,
        strictness=strictness,
        config=config,
        use_cache=use_cache,
        marketplace=marketplace,
        approve_by=approve_by,
        approve_note=approve_note,
    )
    result = engine.run(ctx)

    try:
        assemble_evidence(skill_dir, results=[result], strictness=strictness)
    except OSError:
        pass

    _print_result(result, output=output)
    code = _exit_code(result)
    if code == 2:
        emit(
            FrameworkError(
                summary=f"stage `{stage.value}` engine error",
                detail=result.detail or "engine/framework error",
                fix=resume_hint,
                docs="../docs/recipes/how-to-commands.md",
            )
        )
    return code


def _print_result(result: StageResult, *, output: str) -> None:
    if output == "json":
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
        return
    tag = result.status.value.upper()
    cached = " (cached)" if result.cached else ""
    info(f"  [{tag}] {result.stage}  engine={result.engine.name}{cached}  {result.detail}")
    for f in result.findings[:20]:
        info(f"         · [{f.severity}] {f.message}")


def _exit_code(result: StageResult) -> int:
    if result.status == StageStatus.WAITING:
        return 3
    if result.status == StageStatus.ERROR:
        return 2
    if result.status in {StageStatus.PASSED, StageStatus.SKIPPED}:
        return 0
    return 1


__all__ = ["add_stage_command_args", "resolve_strictness", "run_single_stage"]
