"""`skillctl new <name>` — scaffold a new skill from a strictness-level template.

Phase 1: only the `local` template is wired. Templates are loaded from the
`skillctl.templates` package data (shipped with the wheel) using a Strategy
factory so future templates (team, org, regulated) plug in cleanly.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from ruamel.yaml import YAML

from skillctl.agentskills import validate_name
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.messaging import FrameworkError, emit, info
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    """Wire the `new` subcommand into the CLI."""
    p = subparsers.add_parser(
        "new",
        help="Scaffold a new skill",
        description="Scaffold a new skill at the chosen strictness level.",
    )
    p.add_argument("name", help="Skill name (lowercase, hyphens; max 64 chars)")
    p.add_argument(
        "--strictness",
        default="local",
        choices=[s.value for s in Strictness],
        help="Strictness level to scaffold at (default: local)",
    )
    p.add_argument(
        "--dir",
        default=None,
        help="Parent directory (default: current directory)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute `skillctl new`."""
    name: str = args.name
    strictness = Strictness.from_string(args.strictness)
    parent_dir = Path(args.dir) if args.dir else Path.cwd()

    # Validate name against agentskills.io rules BEFORE creating the directory.
    try:
        validate_name(name)
    except AgentSkillsValidationError as exc:
        emit(
            FrameworkError(
                summary=f"invalid skill name: {exc.message}",
                detail=f"agentskills.io rule violation (code={exc.code})",
                fix=exc.fix,
                docs="https://agentskills.io/specification#name-field",
            )
        )
        return 1

    target = parent_dir / name
    if target.exists():
        emit(
            FrameworkError(
                summary=f"refusing to overwrite existing path: {target}",
                detail="`skillctl new` will not write into an existing directory",
                fix=f"Choose a different name, or remove {target} first.",
            )
        )
        return 1

    skill_md_text = _render_skill_md(
        name=name,
        description=_default_description(name),
        body=_default_body(name),
        strictness=strictness,
    )

    target.mkdir(parents=True, exist_ok=False)
    skill_md_path = target / "SKILL.md"
    skill_md_path.write_text(skill_md_text, encoding="utf-8")

    info(f"Created {skill_md_path}")
    info("")
    info("Next:")
    info(f"  cd {target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target}")
    info("  skillctl compile")
    info("  skillctl run")
    return 0


def _render_skill_md(*, name: str, description: str, body: str, strictness: Strictness) -> str:
    """Render a complete SKILL.md as a string.

    Uses ruamel.yaml to emit the frontmatter so user-supplied values containing
    colons, brackets, leading spaces, etc. are always safely quoted. Naive
    {{var}} substitution silently breaks when descriptions contain `:`.

    The `strictness` argument is plumbed through in case future strictness
    levels need different default frontmatter shapes, but `local` strictness
    only emits the two required fields.
    """
    frontmatter = {"name": name, "description": description}

    yaml = YAML(typ="rt")
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096  # don't wrap long descriptions; the spec allows up to 1024 chars

    buf = io.StringIO()
    yaml.dump(frontmatter, buf)
    frontmatter_text = buf.getvalue().rstrip("\n")

    # Note: future strictness levels may extend the body with additional sections.
    # For local strictness, the body is a single Markdown block.
    _ = strictness  # reserved for future use
    return f"---\n{frontmatter_text}\n---\n\n{body}\n"


def _default_description(name: str) -> str:
    return (
        "Replace this description with a sentence explaining what this skill does and when "
        f"to use it (max 1024 chars). The agent reads this to decide whether to activate {name}."
    )


def _default_body(name: str) -> str:
    return (
        f"# {_humanize(name)}\n"
        "\n"
        "Replace this body with the skill's instructions. Keep it under 500 lines; move "
        "details to `references/` files and load progressively.\n"
    )


def _humanize(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


__all__ = ["register", "run"]
