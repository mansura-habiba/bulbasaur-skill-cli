"""`bbsctl mellea-certify` — certify with the Mellea skills compiler.

Always uses Mellea (compile → certify). Config-driven `bbsctl certify`
still follows `[tool.bbsctl.engines] certify`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.lifecycle.engines.mellea import MelleaEngine
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.stage_cmd import add_stage_command_args, run_single_stage


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "mellea-certify",
        help="Certify a skill with Mellea (compile → certify)",
        description=(
            "Run the Mellea skills compiler: `mellea-skills compile` then "
            "`mellea-skills certify`, and collect audit artifacts.\n\n"
            "Reference: https://github.com/generative-computing/mellea-skills-compiler\n\n"
            "Requires `mellea-skills` on PATH "
            "(`uv sync --group engines` or `uv tool install …`).\n"
            "Config-driven alias: `bbsctl certify` when "
            '`[tool.bbsctl.engines] certify = "mellea"`.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_stage_command_args(
        p,
        strictness_help="Override strictness (regulated adds --enforce)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    return run_single_stage(
        skill_dir=Path(args.skill_dir).resolve(),
        stage=Stage.CERTIFY,
        strictness_override=args.strictness,
        output=args.output,
        use_cache=not args.no_cache,
        engine_override=MelleaEngine(),
        resume_command="mellea-certify",
    )


__all__ = ["register", "run"]
