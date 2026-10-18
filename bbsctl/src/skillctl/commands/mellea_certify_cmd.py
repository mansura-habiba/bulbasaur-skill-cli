"""`bbsctl mellea-certify` — certify with the Mellea skills compiler.

Always uses Mellea (compile → certify). Config-driven `bbsctl certify`
still follows `[tool.bbsctl.engines] certify`.

Models come from `[tool.bbsctl.engines.mellea]` (defaults: ollama + granite
tags). Override per-run with the flags below. Check readiness with
`bbsctl doctor`.
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
            "Requires `mellea-skills` on PATH and a reachable inference engine "
            "(default: Ollama with the configured risk/guardian models).\n"
            "Configure defaults in `[tool.bbsctl.engines.mellea]` or pass the "
            "flags below. `bbsctl doctor` reports which models are ready.\n"
            "Config-driven alias: `bbsctl certify` when "
            '`[tool.bbsctl.engines] certify = "mellea"`.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_stage_command_args(
        p,
        strictness_help="Override strictness (regulated adds --enforce)",
    )
    p.add_argument(
        "--inference-engine",
        default=None,
        help="Override [tool.bbsctl.engines.mellea] inference_engine (default: ollama)",
    )
    p.add_argument(
        "--risk-model",
        default=None,
        help="Override risk_model tag (default: granite4.1:3b)",
    )
    p.add_argument(
        "--guardian-model",
        default=None,
        help="Override guardian_model tag (default: ibm/granite3.3-guardian:8b)",
    )
    p.add_argument(
        "--n-fixtures",
        type=int,
        default=None,
        dest="n_fixtures",
        help="Override n_fixtures for certify (default: 3)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    overrides: dict = {}
    if args.inference_engine is not None:
        overrides["inference_engine"] = args.inference_engine
    if args.risk_model is not None:
        overrides["risk_model"] = args.risk_model
    if args.guardian_model is not None:
        overrides["guardian_model"] = args.guardian_model
    if args.n_fixtures is not None:
        overrides["n_fixtures"] = args.n_fixtures

    return run_single_stage(
        skill_dir=Path(args.skill_dir).resolve(),
        stage=Stage.CERTIFY,
        strictness_override=args.strictness,
        output=args.output,
        use_cache=not args.no_cache,
        engine_override=MelleaEngine(),
        resume_command="mellea-certify",
        mellea_overrides=overrides or None,
    )


__all__ = ["register", "run"]
