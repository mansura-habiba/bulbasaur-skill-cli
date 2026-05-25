"""Parse SKILL.md into structured frontmatter + body.

A SKILL.md file has YAML frontmatter delimited by `---` lines, followed by a
Markdown body. We use ruamel.yaml (round-trippable, YAML 1.2 compliant) so we
can preserve the user's authored frontmatter shape when re-emitting.

The parser is deliberately permissive about whitespace and tolerant of common
mistakes (missing trailing newline, BOM, etc.) — the validator catches spec
violations downstream.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from .rules import (
    AgentSkillsValidationError,
    validate_compatibility,
    validate_description,
    validate_metadata,
    validate_name,
)

_FRONTMATTER_DELIMITER = "---"


@dataclass
class SkillFrontmatter:
    """The structured contents of a SKILL.md file.

    `raw_frontmatter` is the dict as parsed from YAML (with ruamel's preservation).
    `body` is the Markdown content after the frontmatter delimiter.
    `body_line_offset` is the 1-based line number where the body begins, so the
    compiler can produce error messages with accurate line numbers when
    line-numbering the SKILL.md source.
    """

    raw_frontmatter: dict[str, Any]
    body: str
    body_line_offset: int

    # Convenience accessors for spec-required fields.
    @property
    def name(self) -> str | None:
        v = self.raw_frontmatter.get("name")
        return v if isinstance(v, str) else None

    @property
    def description(self) -> str | None:
        v = self.raw_frontmatter.get("description")
        return v if isinstance(v, str) else None

    @property
    def license(self) -> str | None:
        v = self.raw_frontmatter.get("license")
        return v if isinstance(v, str) else None

    @property
    def compatibility(self) -> str | None:
        v = self.raw_frontmatter.get("compatibility")
        return v if isinstance(v, str) else None

    @property
    def metadata(self) -> dict[str, Any] | None:
        v = self.raw_frontmatter.get("metadata")
        return v if isinstance(v, dict) else None

    @property
    def allowed_tools(self) -> str | None:
        # Note: spec uses "allowed-tools" (hyphen) in SKILL.md frontmatter.
        v = self.raw_frontmatter.get("allowed-tools")
        return v if isinstance(v, str) else None


def parse_skill_md(path: str | Path) -> SkillFrontmatter:
    """Read a SKILL.md file and return its parsed frontmatter + body.

    Raises:
        FileNotFoundError: if the path does not exist.
        AgentSkillsValidationError: if the file is missing a valid frontmatter
            block, or the YAML is malformed, or required fields fail validation.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"SKILL.md not found at: {p}")

    text = p.read_text(encoding="utf-8")

    # Strip optional BOM.
    if text.startswith("﻿"):
        text = text.lstrip("﻿")

    lines = text.splitlines(keepends=True)

    if not lines or lines[0].rstrip("\r\n") != _FRONTMATTER_DELIMITER:
        raise AgentSkillsValidationError(
            "frontmatter",
            "missing",
            "SKILL.md must begin with a `---` frontmatter delimiter on line 1",
            fix=(
                "Add YAML frontmatter at the top of the file. Minimal example:\n\n"
                "    ---\n"
                "    name: my-skill\n"
                "    description: What this skill does and when to use it.\n"
                "    ---\n"
                "\n"
                "    Body text here."
            ),
        )

    # Find the closing delimiter.
    closing_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r\n") == _FRONTMATTER_DELIMITER:
            closing_idx = idx
            break

    if closing_idx is None:
        raise AgentSkillsValidationError(
            "frontmatter",
            "unclosed",
            "frontmatter block is not closed by a second `---` delimiter",
            fix="Add a `---` line after the YAML to mark where the body begins.",
        )

    frontmatter_text = "".join(lines[1:closing_idx])
    body = "".join(lines[closing_idx + 1 :])
    body_line_offset = closing_idx + 2  # 1-based: body's first line

    yaml = YAML(typ="rt")
    try:
        parsed = yaml.load(io.StringIO(frontmatter_text)) or {}
    except Exception as exc:
        raise AgentSkillsValidationError(
            "frontmatter",
            "yaml_parse",
            f"failed to parse frontmatter as YAML: {exc}",
            fix=(
                "Check the YAML syntax. Common issues: missing colons, unquoted "
                "values containing colons, inconsistent indentation."
            ),
        ) from exc

    if not isinstance(parsed, dict):
        raise AgentSkillsValidationError(
            "frontmatter",
            "shape",
            "frontmatter must be a YAML mapping (key: value pairs), not a list or scalar",
            fix="Reformat as a mapping. Required keys: `name`, `description`.",
        )

    # Pre-spec checks of required field presence — we want a clear error before
    # the rule validators see a None.
    if "name" not in parsed:
        raise AgentSkillsValidationError(
            "name",
            "required",
            "`name` is required",
            fix="Add `name: my-skill-name` to the frontmatter.",
        )
    if "description" not in parsed:
        raise AgentSkillsValidationError(
            "description",
            "required",
            "`description` is required",
            fix=(
                "Add a `description` field describing what the skill does and "
                "when to use it (≤ 1024 chars)."
            ),
        )

    # Run the spec rules. Each raises AgentSkillsValidationError on violation.
    parent_dir = p.parent.name
    validate_name(parsed["name"], parent_dir=parent_dir)
    validate_description(parsed["description"])
    validate_compatibility(parsed.get("compatibility"))
    validate_metadata(parsed.get("metadata"))

    return SkillFrontmatter(
        raw_frontmatter=dict(parsed),
        body=body,
        body_line_offset=body_line_offset,
    )


__all__ = ["SkillFrontmatter", "parse_skill_md"]
