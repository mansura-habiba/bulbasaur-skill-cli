"""Split a SKILL.md body into canonical authored sections.

Used by the intra-skill conflict analyzer. Deliberately separate from the
private helpers in ``skillctl.audit.checks`` so audit can stay untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .frontmatter import SkillFrontmatter

# Canonical keys the conflict analyzer pairs.
SECTION_DESCRIPTION = "description"
SECTION_WHEN_TO_USE = "when_to_use"
SECTION_INSTRUCTIONS = "instructions"
SECTION_GUARDRAILS = "guardrails"
SECTION_EXAMPLES = "examples"
SECTION_EDGE_CASES = "edge_cases"

_COMPARED_KEYS: tuple[str, ...] = (
    SECTION_DESCRIPTION,
    SECTION_WHEN_TO_USE,
    SECTION_INSTRUCTIONS,
    SECTION_GUARDRAILS,
    SECTION_EXAMPLES,
    SECTION_EDGE_CASES,
)

_DISPLAY_NAMES: dict[str, str] = {
    SECTION_DESCRIPTION: "description",
    SECTION_WHEN_TO_USE: "When to use this skill",
    SECTION_INSTRUCTIONS: "Instructions",
    SECTION_GUARDRAILS: "Guardrails",
    SECTION_EXAMPLES: "Examples",
    SECTION_EDGE_CASES: "Edge cases",
}

# Map normalized ## heading text → canonical key.
_HEADING_ALIASES: dict[str, str] = {
    "when to use this skill": SECTION_WHEN_TO_USE,
    "instructions": SECTION_INSTRUCTIONS,
    "guardrails": SECTION_GUARDRAILS,
    "examples": SECTION_EXAMPLES,
    "edge cases": SECTION_EDGE_CASES,
}

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class SkillSection:
    """One authored section extracted from SKILL.md."""

    key: str
    display_name: str
    text: str
    start_line: int  # 1-based line in the full SKILL.md file


def split_skill_sections(fm: SkillFrontmatter) -> list[SkillSection]:
    """Return non-empty compared sections from parsed frontmatter + body.

    Order follows ``_COMPARED_KEYS``. Unknown ``##`` headings are ignored.
    """
    sections: list[SkillSection] = []

    description = (fm.description or "").strip()
    if description:
        # description lives in frontmatter; approximate as line 2 (after opening ---).
        sections.append(
            SkillSection(
                key=SECTION_DESCRIPTION,
                display_name=_DISPLAY_NAMES[SECTION_DESCRIPTION],
                text=description,
                start_line=2,
            )
        )

    body = fm.body or ""
    if not body.strip():
        return sections

    matches = list(_HEADING_RE.finditer(body))
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        key = _HEADING_ALIASES.get(heading.lower())
        if key is None:
            continue

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        if not text:
            continue

        # Line of the ## heading within the full file.
        lines_before = body[: match.start()].count("\n")
        start_line = fm.body_line_offset + lines_before

        sections.append(
            SkillSection(
                key=key,
                display_name=_DISPLAY_NAMES[key],
                text=text,
                start_line=start_line,
            )
        )

    # Stable order by canonical key list (description first, then body order in _COMPARED_KEYS).
    by_key = {s.key: s for s in sections}
    return [by_key[k] for k in _COMPARED_KEYS if k in by_key]


__all__ = [
    "SECTION_DESCRIPTION",
    "SECTION_EDGE_CASES",
    "SECTION_EXAMPLES",
    "SECTION_GUARDRAILS",
    "SECTION_INSTRUCTIONS",
    "SECTION_WHEN_TO_USE",
    "SkillSection",
    "split_skill_sections",
]
