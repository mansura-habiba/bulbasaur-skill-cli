"""`bbsctl scan` — legacy lightweight scan (bbsctl-audit).

Prefer `bbsctl inspect` for NVIDIA SkillSpector.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.lifecycle.engines.bbsctl_audit import BbsctlAuditEngine
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.stage_cmd import add_stage_command_args, run_single_stage


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "scan",
        help="Legacy scan (bbsctl-audit); prefer `bbsctl inspect`",
        description=(
            "Legacy lightweight scan using the built-in bbsctl-audit engine.\n"
            "For NVIDIA SkillSpector security inspection use `bbsctl inspect`.\n"
            "Reference: https://github.com/NVIDIA/SkillSpector"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_stage_command_args(p)
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    return run_single_stage(
        skill_dir=Path(args.skill_dir).resolve(),
        stage=Stage.SCAN,
        strictness_override=args.strictness,
        output=args.output,
        use_cache=not args.no_cache,
        engine_override=BbsctlAuditEngine(),
        resume_command="scan",
    )


__all__ = ["register", "run"]
