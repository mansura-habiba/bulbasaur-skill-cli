"""`bbsctl author <name>` — AI-assisted skill authoring.

Scaffold a new skill *with content* — not just a template. The composer
runs the configured LLM backend (Ollama by default; no API key required)
to draft the description, the body, and starter eval cases from a one-line
intent.

Examples:

  # Local Ollama, default model
  bbsctl author mq-restarter \\
      --intent "Restart MQ deployments when an alert fires" \\
      --archetype devops --strictness team

  # Use Anthropic
  bbsctl author claim-explainer \\
      --intent "Surface denial reasons from health-claim documents" \\
      --backend anthropic --model claude-sonnet-4-6 \\
      --archetype analytical --strictness org --risk-level high

The output is a complete skill directory the developer iterates on:
SKILL.md, skill.yaml (at team+), permissions.yaml (at team+, archetype-
shaped), evals/behavior.json (3-5 cases). On backend failure the composer
falls back to a `[draft]`-marked skeleton so a missing Ollama doesn't
crash the command.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.authoring import (
    AuthoringError,
    AuthoringRequest,
    SkillArchetype,
    author_skill,
)
from skillctl.llm import list_backends
from skillctl.messaging import FrameworkError, emit, info
from skillctl.skill_yaml import RiskLevel
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "author",
        help="AI-assisted skill authoring — drafts SKILL.md + evals from an intent.",
        description=(
            "Scaffold a new skill with content, not just a template. The composer "
            "runs the configured LLM backend (default: Ollama, no API key) to "
            "draft the description, the body, and starter eval cases from a "
            "one-line intent. Falls back to a marked skeleton on backend failure."
        ),
    )
    p.add_argument("name", help="Skill name (lowercase, hyphens; max 64 chars).")
    p.add_argument(
        "--intent",
        required=True,
        metavar="STR",
        help="One-line description of what the skill should do.",
    )
    p.add_argument(
        "--dir",
        default=".",
        help="Parent directory (default: current directory).",
    )
    p.add_argument(
        "--strictness",
        default="local",
        choices=[s.value for s in Strictness],
        help="Strictness rung for the scaffold (default: local).",
    )
    p.add_argument(
        "--archetype",
        default="analytical",
        choices=[a.value for a in SkillArchetype],
        help=(
            "Skill archetype — shapes the templated permissions.yaml "
            "(default: analytical)."
        ),
    )
    p.add_argument(
        "--risk-level",
        default=None,
        choices=[r.value for r in RiskLevel],
        help="Optional risk level to record in skill.yaml.",
    )
    p.add_argument(
        "--backend",
        default=None,
        choices=list_backends(),
        help="LLM backend (default: configured; ollama if unset).",
    )
    p.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="LLM model (default: configured; backend's default if unset).",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    parent_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    request = AuthoringRequest(
        name=args.name,
        intent=args.intent,
        output_dir=parent_dir,
        strictness=Strictness.from_string(args.strictness),
        archetype=SkillArchetype.from_string(args.archetype),
        backend_name=args.backend,
        model=args.model,
        risk_level=RiskLevel.from_string(args.risk_level),
    )

    try:
        result = author_skill(request)
    except AuthoringError as exc:
        emit(
            FrameworkError(
                summary=f"author: {exc}",
                fix=(
                    "Check the skill name (lowercase + hyphens), make sure "
                    "the target directory does not already exist, and pass "
                    "a non-empty --intent."
                ),
            )
        )
        return 1

    info(f"Created {result.skill_dir}")
    for f in result.files_written:
        info(f"  · {f.relative_to(result.skill_dir.parent)}")
    if result.fell_back_to_skeleton:
        info("")
        info(
            "  (LLM backend was unavailable — wrote a [draft]-marked skeleton. "
            "Replace the [draft] placeholders before publishing.)"
        )
    for note in result.notes:
        info(f"  note: {note}")
    info("")
    info("Next:")
    rel = (
        result.skill_dir.relative_to(Path.cwd())
        if result.skill_dir.is_relative_to(Path.cwd())
        else result.skill_dir
    )
    info(f"  cd {rel}")
    info("  bbsctl compile")
    info("  bbsctl eval")
    return 0


__all__ = ["register", "run"]
