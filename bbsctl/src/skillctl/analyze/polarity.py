"""Deterministic polarity conflict tags across SKILL.md sections.

Tags opposing require/forbid clauses whose leftover content tokens overlap
enough to suggest the same action. Pure and idempotent — no LLM.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from skillctl.agentskills.sections import SkillSection

# Longer forbid phrases first so "must not" wins over "must".
_FORBID_PHRASES: tuple[str, ...] = (
    "must never",
    "must not",
    "must reject",
    "shall not",
    "do not",
    "don't",
    "cannot",
    "never",
)

_REQUIRE_PHRASES: tuple[str, ...] = (
    "required to",
    "always",
    "must",
    "shall",
)

_EXCEPTION_CUES = re.compile(
    r"\b(unless|except|only\s+when)\b",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

_MIN_SHARED_LONG = 2
_MIN_TOKEN_LEN = 4
_MIN_JACCARD = 0.5


@dataclass(frozen=True)
class _Clause:
    section: SkillSection
    polarity: str  # "require" | "forbid"
    span: str
    line: int
    content_tokens: frozenset[str]


@dataclass(frozen=True)
class PolarityConflict:
    """One tagged polarity conflict between two sections."""

    section_a: str
    section_b: str
    quote_a: str
    quote_b: str
    line_a: int
    line_b: int
    shared_tokens: tuple[str, ...]


def find_polarity_conflicts(sections: list[SkillSection]) -> list[PolarityConflict]:
    """Return polarity conflicts for unordered pairs of different sections."""
    clauses_by_section: dict[str, list[_Clause]] = {}
    for section in sections:
        clauses_by_section[section.key] = _extract_clauses(section)

    conflicts: list[PolarityConflict] = []
    keys = [s.key for s in sections]
    display = {s.key: s.display_name for s in sections}

    for key_a, key_b in itertools.combinations(keys, 2):
        for clause_a in clauses_by_section.get(key_a, []):
            for clause_b in clauses_by_section.get(key_b, []):
                if clause_a.polarity == clause_b.polarity:
                    continue
                if _EXCEPTION_CUES.search(clause_a.span) or _EXCEPTION_CUES.search(
                    clause_b.span
                ):
                    continue
                shared = clause_a.content_tokens & clause_b.content_tokens
                long_shared = sorted(t for t in shared if len(t) >= _MIN_TOKEN_LEN)
                if len(long_shared) < _MIN_SHARED_LONG:
                    continue
                union = clause_a.content_tokens | clause_b.content_tokens
                if not union:
                    continue
                jaccard = len(shared) / len(union)
                if jaccard < _MIN_JACCARD:
                    continue

                # Stable section order in the tag: alphabetical display names.
                name_a, name_b = display[key_a], display[key_b]
                if name_a <= name_b:
                    left, right = clause_a, clause_b
                    left_name, right_name = name_a, name_b
                else:
                    left, right = clause_b, clause_a
                    left_name, right_name = name_b, name_a

                conflicts.append(
                    PolarityConflict(
                        section_a=left_name,
                        section_b=right_name,
                        quote_a=_clip(left.span),
                        quote_b=_clip(right.span),
                        line_a=left.line,
                        line_b=right.line,
                        shared_tokens=tuple(long_shared),
                    )
                )

    conflicts.sort(
        key=lambda c: (c.section_a, c.section_b, c.line_a, c.line_b, c.quote_a)
    )
    return conflicts


def _extract_clauses(section: SkillSection) -> list[_Clause]:
    clauses: list[_Clause] = []
    for raw_line in section.text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip list markers.
        line = re.sub(r"^([-*+]|\d+[.)])\s+", "", line)
        line = re.sub(r"^\*\*(.+?)\*\*:?\s*", r"\1: ", line)

        polarity, matched = _match_polarity(line)
        if polarity is None or matched is None:
            continue

        remainder = _strip_phrase(line, matched)
        tokens = _content_tokens(remainder)
        if not tokens:
            continue

        try:
            idx = section.text.splitlines().index(raw_line)
        except ValueError:
            idx = 0
        # description has no ## heading; body sections' start_line is the heading.
        if section.key == "description":
            line_no = section.start_line + idx
        else:
            line_no = section.start_line + 1 + idx

        clauses.append(
            _Clause(
                section=section,
                polarity=polarity,
                span=line,
                line=line_no,
                content_tokens=tokens,
            )
        )
    return clauses


def _match_polarity(text: str) -> tuple[str | None, str | None]:
    lower = text.lower()
    for phrase in _FORBID_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", lower):
            return "forbid", phrase
    for phrase in _REQUIRE_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", lower):
            return "require", phrase
    return None, None


def _strip_phrase(text: str, phrase: str) -> str:
    return re.sub(rf"\b{re.escape(phrase)}\b", " ", text, flags=re.IGNORECASE)


def _content_tokens(text: str) -> frozenset[str]:
    return frozenset(
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) >= _MIN_TOKEN_LEN
    )


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


__all__ = ["PolarityConflict", "find_polarity_conflicts"]
