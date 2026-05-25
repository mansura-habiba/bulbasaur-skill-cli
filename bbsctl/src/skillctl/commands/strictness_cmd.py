"""`bbsctl strictness <level>` — climb the strictness ladder for an existing skill.

Phase 2 supports `team` only. The command:

1. Reads the existing SKILL.md to confirm the skill is valid.
2. Checks / creates `skill.yaml` with the target strictness and prompted fields.
3. Emits a migration diff summary so the developer knows exactly what changed.

The command is *interactive but skippable* — every prompt has a default and
`--yes` (or `-y`) accepts all defaults non-interactively for CI use.

See: framework-build-plan.md §1.3, Phase 2 acceptance #1.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from skillctl.agentskills import parse_skill_md
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.messaging import FrameworkError, emit, info
from skillctl.skill_yaml import (
    OwnershipRef,
    SkillOverlay,
    SkillYamlError,
    load_skill_yaml,
    write_skill_yaml,
)
from skillctl.strictness import Strictness, register_support

# Register `team` as supported for the `strictness` subcommand in the global registry.
register_support("strictness", Strictness.TEAM)


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "strictness",
        help="Climb the strictness ladder for an existing skill",
        description=(
            "Migrate a skill to a higher strictness level. Phase 2 supports `team`.\n"
            "Generates or updates skill.yaml with the required fields."
        ),
    )
    p.add_argument(
        "level",
        choices=["team"],  # org/regulated land in Phase 3/5
        help="Target strictness level",
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    p.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Accept all defaults without prompting (for CI / non-interactive use)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    target = Strictness.from_string(args.level)
    non_interactive = args.yes or not _is_interactive()

    # ── 1. Verify SKILL.md ──────────────────────────────────────────────
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        emit(
            FrameworkError(
                summary="SKILL.md not found",
                detail=f"expected at {skill_md}",
                fix="Run `bbsctl new <name>` to scaffold a skill first.",
            )
        )
        return 1

    try:
        frontmatter = parse_skill_md(skill_md)
    except AgentSkillsValidationError as exc:
        emit(
            FrameworkError(
                summary=f"SKILL.md is invalid: {exc.message}",
                fix=f"{exc.fix}  Run `bbsctl compile` to see all errors.",
                docs="https://agentskills.io/specification",
            )
        )
        return 1

    skill_name = frontmatter.name or skill_dir.name

    # ── 2. Load or create skill.yaml ────────────────────────────────────
    skill_yaml_path = skill_dir / "skill.yaml"
    existing: SkillOverlay | None = None
    try:
        existing = load_skill_yaml(skill_dir)
    except SkillYamlError as exc:
        emit(exc.framework_error)
        return 1

    already_at_target = existing is not None and existing.strictness.includes(target)
    if already_at_target:
        info(f"skill `{skill_name}` is already at {target.value} strictness.")
        info(f"  skill.yaml: {skill_yaml_path}")
        return 0

    # ── 3. Interactive ownership prompt ─────────────────────────────────
    info(f"Migrating `{skill_name}` to {target.value} strictness.")
    info("")

    ownership = _prompt_ownership(skill_name, non_interactive=non_interactive)

    # ── 4. Write skill.yaml ─────────────────────────────────────────────
    overlay = SkillOverlay(
        name=skill_name,
        strictness=target,
        version=existing.version if existing else "0.1.0",
        ownership=ownership,
        marketplace=existing.marketplace if existing else None,
        output_contract=existing.output_contract if existing else None,
        model_compatibility=existing.model_compatibility if existing else [],
    )

    write_skill_yaml(skill_yaml_path, overlay)

    # ── 5. Summary ───────────────────────────────────────────────────────
    info("")
    if skill_yaml_path.exists():
        action = "Updated" if existing else "Created"
        info(f"{action} {skill_yaml_path}")
    _print_migration_summary(skill_name, target, ownership)
    return 0


def _prompt_ownership(skill_name: str, *, non_interactive: bool) -> OwnershipRef | None:
    """Prompt for ownership details. Returns None if user skips."""
    info("Ownership (recommended at team; required at org+).")
    info("  Press Enter to skip any field, or `-y` to skip all prompts.")
    info("")

    if non_interactive:
        info("  (--yes: skipping ownership prompts)")
        return None

    team = _prompt("  Owner team name", default="")
    if not team:
        info("  Ownership skipped. You can add it later by editing skill.yaml.")
        return None

    contact = _prompt("  Contact email or Slack", default="")
    runbook = _prompt("  Runbook URL", default="")

    return OwnershipRef(
        team=team or None,
        contact=contact or None,
        runbook=runbook or None,
    )


def _prompt(label: str, *, default: str) -> str:
    """Read one interactive input line with a default."""
    suffix = f" [{default}]" if default else ""
    try:
        return input(f"{label}{suffix}: ").strip() or default
    except (EOFError, KeyboardInterrupt):
        return default


def _is_interactive() -> bool:
    """Return True if stdin appears to be a TTY."""
    return os.isatty(0)


def _print_migration_summary(
    skill_name: str,
    target: Strictness,
    ownership: OwnershipRef | None,
) -> None:
    info(f"skill `{skill_name}` is now at {target.value} strictness.")
    info("")
    info("What changed:")
    info("  + skill.yaml created/updated with strictness: team")
    if ownership and ownership.team:
        info(f"  + ownership.team = {ownership.team!r}")
    else:
        info("  ~ ownership not set (add `ownership:` in skill.yaml when ready)")
    info("")
    info("Next steps:")
    info("  bbsctl validate --fast          # run team-tier validators")
    info("  bbsctl publish --marketplace <path>  # publish to team marketplace")


__all__ = ["register", "run"]
