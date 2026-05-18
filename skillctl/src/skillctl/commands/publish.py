"""`bbsctl publish` — emit the skill via a publish target.

The target is a PublishTarget strategy (see skillctl.publish). Phase 1 ships:

  claude-code-local   local Claude Code marketplace; demo path, no API key

Phase 2-3 add: claude-code-remote, mcp-composer, oci.

The subcommand stays small. Target-specific options come in via `--option k=v`
so adding a target does not bloat the CLI surface.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.agentskills import parse_skill_md
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.messaging import FrameworkError, emit, info
from skillctl.publish import build_target, list_targets
from skillctl.publish.factory import target_description
from skillctl.publish.target import PublishContext
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    """Wire the `publish` subcommand into the CLI."""
    target_help = " | ".join(f"{name}: {target_description(name)}" for name in list_targets())
    p = subparsers.add_parser(
        "publish",
        help="Publish the skill via a target adapter",
        description=(
            "Emit the skill as an artifact a target can consume. "
            "Phase 1 default target is `claude-code-local`."
        ),
        epilog=f"Available targets:\n  {target_help}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    p.add_argument(
        "--target",
        default="claude-code-local",
        choices=list_targets(),
        help="Publish target (default: claude-code-local)",
    )
    p.add_argument(
        "--output",
        default=None,
        help=(
            "Output directory for the target's artifacts. "
            "For claude-code-local, default is `./bulbasaur-marketplace` next to CWD."
        ),
    )
    p.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Target-specific option (repeatable). E.g. `--option marketplace_name=acme`.",
    )
    p.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help="Override strictness for this publish (default: read from skill.yaml or LOCAL)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute `bbsctl publish`."""
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
        frontmatter = parse_skill_md(skill_md)
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

    options = _parse_options(args.option)
    if options is None:
        return 1  # error already emitted

    try:
        target = build_target(args.target)
    except ValueError as exc:
        emit(
            FrameworkError(
                summary="unknown publish target",
                detail=str(exc),
                fix=f"Pick one of: {', '.join(list_targets())}",
            )
        )
        return 1

    output_dir = _resolve_output_dir(args.output, target_name=args.target, skill_dir=skill_dir)
    strictness = Strictness.from_string(args.strictness)

    # Strictness floor enforcement — refuse if the target needs more than the skill declares.
    if not strictness.includes(target.min_strictness):
        emit(
            FrameworkError(
                summary=f"target `{args.target}` requires strictness ≥ {target.min_strictness.value}",
                detail=f"this skill is at strictness {strictness.value}",
                fix=(
                    f"Run `bbsctl strictness {target.min_strictness.value}` first to "
                    "climb the ladder, or pick a target with a lower floor "
                    "(e.g. `--target claude-code-local`)."
                ),
            )
        )
        return 1

    context = PublishContext(
        skill_dir=skill_dir,
        frontmatter=frontmatter,
        strictness=strictness,
        output_dir=output_dir,
        target_options=options,
    )

    result = target.publish(context)
    _print_result(result)
    return 0 if result.success else 1


def _parse_options(raw: list[str]) -> dict[str, str] | None:
    """Parse repeated `--option k=v` args into a dict.

    Returns None and emits an error on malformed input.
    """
    out: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            emit(
                FrameworkError(
                    summary=f"malformed --option value: {item!r}",
                    fix="Use the form `--option key=value` (e.g. `--option marketplace_name=acme`).",
                )
            )
            return None
        key, value = item.split("=", 1)
        out[key.strip()] = value
    return out


def _resolve_output_dir(override: str | None, *, target_name: str, skill_dir: Path) -> Path:
    """Resolve the output directory for the target, with sensible per-target defaults."""
    if override:
        return Path(override).resolve()

    if target_name == "claude-code-local":
        # Sibling to the skill directory keeps the demo self-contained.
        return (skill_dir.parent / "bulbasaur-marketplace").resolve()

    return (skill_dir / "dist" / target_name).resolve()


def _print_result(result) -> None:
    """Render a PublishResult to stdout following the messaging conventions."""
    if result.success:
        info(f"published via {result.target_name}")
        for label, path in result.artifacts.items():
            info(f"  · {label}: {path}")
        if result.next_steps:
            info("")
            info("Next steps:")
            for line in result.next_steps:
                info(f"  {line}" if line else "")
    else:
        info(f"publish failed (target={result.target_name})")
        for line in result.next_steps:
            info(f"  {line}")


__all__ = ["register", "run"]
