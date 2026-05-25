"""`bbsctl new <name>` — scaffold a new skill from the agentskills.io spec.

Reads the field definitions from agentskills-spec.yaml and generates a
spec-compliant SKILL.md with:
  - Required fields filled with placeholders
  - Optional fields included as commented YAML the developer can uncomment
  - Body sections following the spec's recommended structure
  - The spec-recommended directory layout (references/, etc.)

The result is a contract: every field the spec defines is visible in the
scaffolded file, and the developer fills in what they need.
"""

from __future__ import annotations

import argparse
import importlib.resources
import io
from pathlib import Path

from ruamel.yaml import YAML

from skillctl.agentskills import validate_name
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.agentskills.spec import load_spec
from skillctl.messaging import FrameworkError, emit, info
from skillctl.skill_yaml import SkillOverlay, write_skill_yaml
from skillctl.strictness import (
    Strictness,
    fail_if_unsupported,
    register_support,
    supported_levels,
)

register_support("new", Strictness.TEAM)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Wire the `new` subcommand into the CLI."""
    p = subparsers.add_parser(
        "new",
        help="Scaffold a new skill",
        description=(
            "Scaffold a new skill from the agentskills.io spec. "
            "All spec fields are included as placeholders."
        ),
    )
    p.add_argument(
        "name", help="Skill name (lowercase, hyphens; max 64 chars)"
    )
    p.add_argument(
        "--strictness",
        default="local",
        choices=supported_levels("new"),
        help="Strictness level (default: local).",
    )
    p.add_argument(
        "--dir",
        default=None,
        help="Parent directory (default: current directory)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute `bbsctl new`."""
    name: str = args.name
    strictness = Strictness.from_string(args.strictness)
    parent_dir = Path(args.dir) if args.dir else Path.cwd()

    unsupported_fix = fail_if_unsupported("new", strictness)
    if unsupported_fix is not None:
        emit(
            FrameworkError(
                summary=(
                    f"strictness `{strictness.value}` is not "
                    "supported by `bbsctl new` yet"
                ),
                detail="vapor-options guard",
                fix=unsupported_fix,
                docs="../docs/strictness-levels.md",
            )
        )
        return 1

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
                detail="`bbsctl new` will not write into an existing directory",
                fix=f"Choose a different name, or remove {target} first.",
            )
        )
        return 1

    spec = load_spec()

    skill_md_text = _render_skill_md(
        name=name, strictness=strictness, spec=spec
    )

    target.mkdir(parents=True, exist_ok=False)

    # Scaffold spec-recommended directories.
    for d in spec.directories:
        (target / d.name).mkdir()
        (target / d.name / ".gitkeep").touch()

    skill_md_path = target / "SKILL.md"
    skill_md_path.write_text(skill_md_text, encoding="utf-8")
    info(f"Created {skill_md_path}")

    if strictness.includes(Strictness.TEAM):
        _scaffold_skill_yaml(target, name=name, strictness=strictness)

    info("")
    info("Next:")
    rel = (
        target.relative_to(Path.cwd())
        if target.is_relative_to(Path.cwd())
        else target
    )
    info(f"  cd {rel}")
    info("  bbsctl compile")
    if strictness.includes(Strictness.TEAM):
        info("  bbsctl validate --fast")
    info("  bbsctl run")
    return 0


def _render_skill_md(*, name: str, strictness: Strictness, spec) -> str:
    """Render a spec-compliant SKILL.md with all fields as placeholders.

    Required fields are filled with placeholder values.
    Optional fields are included as YAML comments the developer can
    uncomment and fill in — making the full contract visible.
    """
    # Build frontmatter via ruamel.yaml for safe quoting.
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096

    frontmatter: dict = {}
    for f in spec.required_fields():
        if f.name == "name":
            frontmatter[f.name] = name
        elif f.name == "description":
            human = _humanize(name)
            frontmatter[f.name] = (
                f"[What {human} does]. "
                f"Use when [the trigger situation for {name}]."
            )
        else:
            frontmatter[f.name] = f.placeholder or f"[{f.name}]"

    buf = io.StringIO()
    yaml.dump(frontmatter, buf)
    required_yaml = buf.getvalue().rstrip("\n")

    # Build commented-out optional fields with examples.
    optional_lines: list[str] = []
    for f in spec.optional_fields():
        optional_lines.append(f"# {f.name}: {_format_placeholder(f)}")

    optional_block = "\n".join(optional_lines)

    # Build the body from the template.
    body = _load_template_body(name, strictness)

    # Assemble.
    parts = ["---", required_yaml]
    if optional_lines:
        parts.append("")
        parts.append(
            "# Optional fields — uncomment and fill in as needed."
        )
        parts.append(
            f"# Full spec: {spec.spec_url}"
        )
        parts.append(optional_block)
    parts.append("---")
    parts.append("")
    parts.append(body)

    return "\n".join(parts) + "\n"


def _format_placeholder(f) -> str:
    """Format a placeholder value for a commented YAML field."""
    if f.type == "mapping" and isinstance(f.placeholder, dict):
        # Multi-line mapping as commented YAML.
        lines = [f.placeholder.__class__.__name__]
        lines = []
        first = True
        for k, v in f.placeholder.items():
            if first:
                lines.append("")
                first = False
            lines.append(f"#   {k}: {_quote_if_needed(v)}")
        return "\n".join(lines)
    if f.placeholder is not None:
        return str(f.placeholder)
    if f.example is not None:
        return str(f.example)
    return f"[{f.name}]"


def _quote_if_needed(v) -> str:
    """Quote a value if it looks like it needs YAML quoting."""
    s = str(v)
    if any(c in s for c in ":{}[],"): 
        return f'"{s}"'
    return s


def _load_template_body(name: str, strictness: Strictness) -> str:
    """Load the body portion of the SKILL.md template for a strictness level."""
    level = strictness.value
    try:
        pkg = f"skillctl.templates.{level}"
        tmpl = (
            importlib.resources.files(pkg)
            .joinpath("SKILL.md.template")
            .read_text(encoding="utf-8")
        )
    except (ModuleNotFoundError, FileNotFoundError):
        pkg = "skillctl.templates.local"
        tmpl = (
            importlib.resources.files(pkg)
            .joinpath("SKILL.md.template")
            .read_text(encoding="utf-8")
        )

    body = _strip_frontmatter(tmpl)
    return body.replace("{{name}}", name).replace(
        "{{title}}", _humanize(name)
    )


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from a template string."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            remainder = "\n".join(lines[i + 1 :])
            return remainder.lstrip("\n")
    return text


def _humanize(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def _scaffold_skill_yaml(
    skill_dir: Path, *, name: str, strictness: Strictness
) -> None:
    """Write a starter skill.yaml alongside SKILL.md for team+ strictness."""
    overlay = SkillOverlay(
        name=name,
        strictness=strictness,
        version="0.1.0",
        ownership=None,
    )
    skill_yaml_path = skill_dir / "skill.yaml"
    write_skill_yaml(skill_yaml_path, overlay)
    info(f"Created {skill_yaml_path}")


__all__ = ["register", "run"]
