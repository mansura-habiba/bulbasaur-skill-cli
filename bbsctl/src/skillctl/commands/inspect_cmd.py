"""`bbsctl inspect` — NVIDIA SkillSpector security inspection.

Preferred inspect path. Legacy lightweight scan remains `bbsctl scan`
(bbsctl-audit).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.lifecycle.engines.skillspector import SkillspectorEngine
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.stage_cmd import add_stage_command_args, run_single_stage


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "inspect",
        help="Inspect a skill with NVIDIA SkillSpector",
        description=(
            "Run NVIDIA SkillSpector against the skill and normalise SARIF "
            "into a StageResult.\n\n"
            "Reference: https://github.com/NVIDIA/SkillSpector\n\n"
            "Requires Python >= 3.12 and `skillspector` on PATH "
            "(`uv sync --group engines` or `uv tool install …`).\n"
            "Always passes `--no-llm` — no model or API key is required.\n"
            "Legacy lightweight scan: `bbsctl scan` (bbsctl-audit)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_stage_command_args(
        p,
        strictness_help="Override strictness (regulated adds --fail-on-findings)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    return run_single_stage(
        skill_dir=Path(args.skill_dir).resolve(),
        stage=Stage.SCAN,
        strictness_override=args.strictness,
        output=args.output,
        use_cache=not args.no_cache,
        engine_override=SkillspectorEngine(),
        resume_command="inspect",
    )


__all__ = ["register", "run"]
