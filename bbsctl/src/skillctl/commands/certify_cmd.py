"""`bbsctl certify` — run the certify stage (config-driven engine).

Prefer `bbsctl mellea-certify` to force the Mellea skills compiler.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.stage_cmd import add_stage_command_args, run_single_stage


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "certify",
        help="Certify a skill (engine from config; prefer mellea-certify)",
        description=(
            "Run the certify stage using `[tool.bbsctl.engines] certify` "
            '(default: `"none"`; set `"mellea"` to enable).\n\n'
            "To always use Mellea regardless of config, run "
            "`bbsctl mellea-certify`.\n"
            "Reference: https://github.com/generative-computing/mellea-skills-compiler"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_stage_command_args(
        p,
        strictness_help="Override strictness (regulated adds --enforce for Mellea)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    return run_single_stage(
        skill_dir=Path(args.skill_dir).resolve(),
        stage=Stage.CERTIFY,
        strictness_override=args.strictness,
        output=args.output,
        use_cache=not args.no_cache,
        resume_command="certify",
    )


__all__ = ["register", "run"]
