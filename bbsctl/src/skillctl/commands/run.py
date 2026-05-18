"""`bbsctl run` — execute a skill against a runtime adapter.

Phase 1 ships the mock runtime so the quickstart works with zero external
dependencies. Later phases register Claude Agent SDK, Claude Code, MCP, and
LangGraph adapters through `skillctl.run.register_runtime`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.agentskills import parse_skill_md
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.messaging import FrameworkError, emit, info
from skillctl.run import build_runtime
from skillctl.run.factory import list_runtimes


_DEFAULT_PROMPT = "hello"


def register(subparsers: argparse._SubParsersAction) -> None:
    """Wire the `run` subcommand into the CLI."""
    p = subparsers.add_parser(
        "run",
        help="Execute the skill against a runtime adapter",
        description="Activate the skill in the current directory against a runtime.",
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    p.add_argument(
        "--runtime",
        default="mock",
        choices=list_runtimes(),
        help="Runtime adapter (default: mock)",
    )
    p.add_argument(
        "--prompt",
        default=_DEFAULT_PROMPT,
        help=f"Prompt to send to the agent (default: {_DEFAULT_PROMPT!r})",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute `bbsctl run`."""
    skill_dir = Path(args.skill_dir).resolve()
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        emit(
            FrameworkError(
                summary=f"SKILL.md not found at {skill_md}",
                fix="Run `bbsctl new <name>` to scaffold a skill, or `cd` into one first.",
            )
        )
        return 1

    try:
        skill = parse_skill_md(skill_md)
    except AgentSkillsValidationError as exc:
        emit(
            FrameworkError(
                summary=f"{exc.field}: {exc.message}",
                detail=f"agentskills.io rule violation (code={exc.code})",
                fix=exc.fix,
                docs="https://agentskills.io/specification",
            )
        )
        return 1

    runtime = build_runtime(args.runtime)
    response = runtime.activate(skill, args.prompt)

    for trace_line in response.trace:
        info(trace_line)
    return 0


__all__ = ["register", "run"]
