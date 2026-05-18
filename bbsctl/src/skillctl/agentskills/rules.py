"""Validation rules from https://agentskills.io/specification.

These are pure functions that take a value and return None on success or raise
AgentSkillsValidationError on failure. They are intentionally separate from
the frontmatter parser so they can be reused (in `bbsctl new`, in the
validator, in the LSP, etc.).

Source-of-truth: https://agentskills.io/specification

Required frontmatter fields:
  name         Max 64 chars; lowercase letters, digits, hyphens; no leading/
               trailing or consecutive hyphens. Must match parent directory.
  description  Max 1024 chars; non-empty.

Optional fields:
  license        License name or path to bundled file.
  compatibility  Max 500 chars.
  metadata       Arbitrary string-keyed map.
  allowed-tools  Space-separated string (Experimental).
"""

from __future__ import annotations

import re
from typing import Any

AGENTSKILLS_SPEC_URL = "https://agentskills.io/specification"

# Per spec: 1-64 chars, lowercase letters / digits / hyphens, no leading or
# trailing hyphen, no consecutive hyphens.
# We compile this once at import time.
_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_NAME_MIN = 1
_NAME_MAX = 64

_DESCRIPTION_MIN = 1
_DESCRIPTION_MAX = 1024

_COMPATIBILITY_MIN = 1
_COMPATIBILITY_MAX = 500

# Mellea's metadata.instructions convention (mcp-composer-analysis §6) — we
# adopt the same cap for portability.
_METADATA_INSTRUCTIONS_MAX = 2048


class AgentSkillsValidationError(ValueError):
    """A violation of the agentskills.io spec.

    Carries a structured `field`, `code`, and human-readable `message` so the
    CLI can format the error with the Bulbasaur error contract.
    """

    def __init__(self, field: str, code: str, message: str, *, fix: str | None = None):
        self.field = field
        self.code = code
        self.message = message
        self.fix = fix
        super().__init__(f"{field}: {message}")


def validate_name(value: Any, *, parent_dir: str | None = None) -> None:
    """Validate the `name` field per agentskills.io spec.

    If `parent_dir` is provided, also enforces "name must match parent directory."
    """
    if not isinstance(value, str):
        raise AgentSkillsValidationError(
            "name",
            "type",
            f"must be a string (got {type(value).__name__})",
            fix="Quote the value as a string in the YAML frontmatter.",
        )

    if not (_NAME_MIN <= len(value) <= _NAME_MAX):
        raise AgentSkillsValidationError(
            "name",
            "length",
            f"must be {_NAME_MIN}-{_NAME_MAX} chars (got {len(value)})",
            fix=f"Trim or pad the name to fit {_NAME_MIN}-{_NAME_MAX} chars.",
        )

    if not _NAME_PATTERN.fullmatch(value):
        # Try to be specific about which rule failed.
        if value.startswith("-") or value.endswith("-"):
            detail = "must not start or end with a hyphen"
        elif "--" in value:
            detail = "must not contain consecutive hyphens"
        elif any(c.isupper() for c in value):
            detail = "must be lowercase (no uppercase letters)"
        elif any(c == "_" for c in value):
            detail = "must use hyphens, not underscores"
        else:
            detail = "may only contain lowercase letters, digits, and hyphens"

        raise AgentSkillsValidationError(
            "name",
            "pattern",
            detail,
            fix=f"Rename to a lowercase kebab-case identifier (e.g. `my-skill`).",
        )

    if parent_dir is not None and value != parent_dir:
        raise AgentSkillsValidationError(
            "name",
            "parent_mismatch",
            f"must match the parent directory name (skill name={value!r}, directory={parent_dir!r})",
            fix=f"Rename the directory to `{value}` or change the name field to `{parent_dir}`.",
        )


def validate_description(value: Any) -> None:
    """Validate the `description` field per agentskills.io spec."""
    if not isinstance(value, str):
        raise AgentSkillsValidationError(
            "description",
            "type",
            f"must be a string (got {type(value).__name__})",
            fix="Quote the value as a string in the YAML frontmatter.",
        )

    stripped = value.strip()
    if len(stripped) < _DESCRIPTION_MIN:
        raise AgentSkillsValidationError(
            "description",
            "empty",
            "must be non-empty",
            fix="Write one or two sentences describing what the skill does and when to use it.",
        )

    if len(value) > _DESCRIPTION_MAX:
        raise AgentSkillsValidationError(
            "description",
            "length",
            f"must be ≤ {_DESCRIPTION_MAX} chars (got {len(value)})",
            fix=(
                f"Trim to {_DESCRIPTION_MAX} chars, or split into multiple skills "
                "with sharper boundaries. The agentskills.io spec requires this cap."
            ),
        )


def validate_compatibility(value: Any) -> None:
    """Validate the optional `compatibility` field per agentskills.io spec."""
    if value is None:
        return
    if not isinstance(value, str):
        raise AgentSkillsValidationError(
            "compatibility",
            "type",
            f"must be a string (got {type(value).__name__})",
            fix="Quote the value as a string in the YAML frontmatter.",
        )
    if not (_COMPATIBILITY_MIN <= len(value) <= _COMPATIBILITY_MAX):
        raise AgentSkillsValidationError(
            "compatibility",
            "length",
            f"must be {_COMPATIBILITY_MIN}-{_COMPATIBILITY_MAX} chars (got {len(value)})",
            fix=(
                f"Trim or remove the `compatibility` field. The agentskills.io spec "
                f"caps it at {_COMPATIBILITY_MAX} chars."
            ),
        )


def validate_metadata(value: Any) -> None:
    """Validate the optional `metadata` field per agentskills.io spec.

    Spec: arbitrary key-value mapping. We additionally enforce the Mellea-
    derived 2048-char cap on `metadata.instructions` if present (for
    portability with MCP Composer; see mcp-composer-analysis §6).
    """
    if value is None:
        return
    if not isinstance(value, dict):
        raise AgentSkillsValidationError(
            "metadata",
            "type",
            f"must be a key-value map (got {type(value).__name__})",
            fix="Format as a YAML mapping, e.g. `metadata:\\n  key: value`.",
        )

    instructions = value.get("instructions")
    if instructions is not None:
        if not isinstance(instructions, str):
            raise AgentSkillsValidationError(
                "metadata.instructions",
                "type",
                f"must be a string (got {type(instructions).__name__})",
                fix="Quote the value as a string in the YAML frontmatter.",
            )
        if len(instructions) > _METADATA_INSTRUCTIONS_MAX:
            raise AgentSkillsValidationError(
                "metadata.instructions",
                "length",
                f"must be ≤ {_METADATA_INSTRUCTIONS_MAX} chars (got {len(instructions)})",
                fix=(
                    f"Trim `metadata.instructions` to {_METADATA_INSTRUCTIONS_MAX} chars or "
                    "move long content into `references/` files and load progressively."
                ),
            )


__all__ = [
    "AGENTSKILLS_SPEC_URL",
    "AgentSkillsValidationError",
    "validate_name",
    "validate_description",
    "validate_compatibility",
    "validate_metadata",
]
