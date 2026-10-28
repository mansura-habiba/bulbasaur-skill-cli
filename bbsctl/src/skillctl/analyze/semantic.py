"""Optional LLM semantic conflict tags across SKILL.md sections.

Quotes must be exact substrings of the two section texts (grounding).
Backend failures are surfaced to the caller; they must not fail validate.
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass

from skillctl.agentskills.sections import SkillSection
from skillctl.llm.base import LLMBackend, LLMBackendError

_SYSTEM = (
    "You find contradictions between two sections of the same agent skill file. "
    "A contradiction is when the sections give opposing instructions about the "
    "same action or policy. Reply with JSON only."
)

_USER_TEMPLATE = """\
Section A ({name_a}):
---
{text_a}
---

Section B ({name_b}):
---
{text_b}
---

Return a JSON object:
{{"conflicts": [{{"quote_a": "...", "quote_b": "...", "reason": "..."}}]}}

Rules:
- quote_a must be an exact substring of Section A.
- quote_b must be an exact substring of Section B.
- If there is no contradiction, return {{"conflicts": []}}.
"""


@dataclass(frozen=True)
class SemanticConflict:
    """One grounded semantic conflict between two sections."""

    section_a: str
    section_b: str
    quote_a: str
    quote_b: str
    reason: str


def find_semantic_conflicts(
    sections: list[SkillSection],
    backend: LLMBackend,
    *,
    model: str | None = None,
) -> tuple[list[SemanticConflict], str | None]:
    """Run the LLM over section pairs.

    Returns ``(conflicts, skip_note)``. ``skip_note`` is set when the backend
    errors; partial conflicts from earlier pairs are still returned.
    """
    conflicts: list[SemanticConflict] = []
    skip_note: str | None = None
    display = {s.key: s.display_name for s in sections}

    for sec_a, sec_b in itertools.combinations(sections, 2):
        prompt = _USER_TEMPLATE.format(
            name_a=sec_a.display_name,
            text_a=sec_a.text,
            name_b=sec_b.display_name,
            text_b=sec_b.text,
        )
        try:
            response = backend.complete(
                prompt=prompt,
                model=model,
                system=_SYSTEM,
                max_tokens=1024,
                temperature=0.0,
            )
        except LLMBackendError as exc:
            skip_note = f"semantic conflict pass skipped: {exc}"
            break
        except Exception as exc:  # pragma: no cover — defensive
            skip_note = f"semantic conflict pass skipped: {exc}"
            break

        for item in _parse_conflicts(response.text):
            quote_a = str(item.get("quote_a") or "")
            quote_b = str(item.get("quote_b") or "")
            reason = str(item.get("reason") or "").strip()
            if not quote_a or not quote_b:
                continue
            if quote_a not in sec_a.text or quote_b not in sec_b.text:
                # Grounding check — drop hallucinated quotes.
                continue

            name_a, name_b = display[sec_a.key], display[sec_b.key]
            if name_a <= name_b:
                left_name, right_name = name_a, name_b
                left_q, right_q = quote_a, quote_b
            else:
                left_name, right_name = name_b, name_a
                left_q, right_q = quote_b, quote_a

            conflicts.append(
                SemanticConflict(
                    section_a=left_name,
                    section_b=right_name,
                    quote_a=_clip(left_q),
                    quote_b=_clip(right_q),
                    reason=reason or "semantic contradiction",
                )
            )

    conflicts.sort(key=lambda c: (c.section_a, c.section_b, c.quote_a, c.quote_b))
    return conflicts, skip_note


def _parse_conflicts(text: str) -> list[dict]:
    payload = _extract_json(text)
    if not isinstance(payload, dict):
        return []
    raw = payload.get("conflicts")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _extract_json(text: str) -> object | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            return None
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


__all__ = ["SemanticConflict", "find_semantic_conflicts"]
