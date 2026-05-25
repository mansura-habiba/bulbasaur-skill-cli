"""Load the agentskills.io spec definition from agentskills-spec.yaml.

The spec YAML is the single source of truth for field definitions,
constraints, placeholders, and directory structure. This module exposes
the parsed spec as typed dataclasses that the scaffolder (bbsctl new),
the validator (bbsctl compile / validate), and the templates consume.
"""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml import YAML

_SPEC_CACHE: SkillSpec | None = None


@dataclass
class FieldSpec:
    """One frontmatter field from the agentskills.io spec."""

    name: str
    required: bool
    type: str
    description: str
    placeholder: Any = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    rules: list[str] = field(default_factory=list)
    guidance: list[str] = field(default_factory=list)
    example: Any = None


@dataclass
class DirSpec:
    """One recommended directory from the spec."""

    name: str
    required: bool
    description: str
    recommended_files: list[str] = field(default_factory=list)


@dataclass
class BodySection:
    """One section in the SKILL.md body."""

    title: str
    description: str
    required: bool = False


@dataclass
class SkillSpec:
    """The full parsed agentskills.io specification."""

    spec_url: str
    spec_version: str
    fields: list[FieldSpec]
    directories: list[DirSpec]
    body_max_lines: int
    required_body_sections: list[BodySection]
    optional_body_sections: list[BodySection]

    def required_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.required]

    def optional_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if not f.required]

    def field_by_name(self, name: str) -> FieldSpec | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None


def load_spec() -> SkillSpec:
    """Load and cache the agentskills-spec.yaml."""
    global _SPEC_CACHE
    if _SPEC_CACHE is not None:
        return _SPEC_CACHE

    raw_text = (
        importlib.resources.files("skillctl.agentskills")
        .joinpath("agentskills-spec.yaml")
        .read_text(encoding="utf-8")
    )
    yaml = YAML(typ="safe")
    raw = yaml.load(raw_text)

    fields: list[FieldSpec] = []
    for name, fdef in raw["fields"].items():
        fields.append(
            FieldSpec(
                name=name,
                required=fdef.get("required", False),
                type=fdef.get("type", "string"),
                description=fdef.get("description", ""),
                placeholder=fdef.get("placeholder"),
                min_length=fdef.get("min_length"),
                max_length=fdef.get("max_length"),
                pattern=fdef.get("pattern"),
                rules=fdef.get("rules", []),
                guidance=fdef.get("guidance", []),
                example=fdef.get("example"),
            )
        )

    directories: list[DirSpec] = []
    for name, ddef in raw.get("directories", {}).items():
        directories.append(
            DirSpec(
                name=name,
                required=ddef.get("required", False),
                description=ddef.get("description", ""),
                recommended_files=ddef.get("recommended_files", []),
            )
        )

    body_cfg = raw.get("body", {})
    required_sections = [
        BodySection(
            title=s["title"],
            description=s["description"],
            required=True,
        )
        for s in body_cfg.get("required_sections", [])
    ]
    optional_sections = [
        BodySection(
            title=s["title"],
            description=s["description"],
            required=False,
        )
        for s in body_cfg.get("optional_sections", [])
    ]

    _SPEC_CACHE = SkillSpec(
        spec_url=raw.get("spec_url", ""),
        spec_version=raw.get("spec_version", ""),
        fields=fields,
        directories=directories,
        body_max_lines=body_cfg.get("max_lines", 500),
        required_body_sections=required_sections,
        optional_body_sections=optional_sections,
    )
    return _SPEC_CACHE


__all__ = [
    "BodySection",
    "DirSpec",
    "FieldSpec",
    "SkillSpec",
    "load_spec",
]
