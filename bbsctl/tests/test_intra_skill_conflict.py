"""Unit tests for intra-SKILL.md conflict tags (gh-18)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from skillctl.agentskills.frontmatter import parse_skill_md
from skillctl.agentskills.sections import split_skill_sections
from skillctl.analyze.polarity import find_polarity_conflicts
from skillctl.analyze.semantic import find_semantic_conflicts
from skillctl.llm.base import LLMBackend, LLMBackendError, LLMResponse
from skillctl.strictness import Strictness
from skillctl.validate import ValidateMode, ValidateRunner
from skillctl.validate.intra_skill_conflict import IntraSkillConflictValidator


def _write_skill(skill_dir: Path, body: str, *, name: str | None = None) -> Path:
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_name = name or skill_dir.name
    skill_dir.joinpath("SKILL.md").write_text(
        textwrap.dedent(body).replace("{{name}}", skill_name),
        encoding="utf-8",
    )
    return skill_dir


def _conflict_summaries(result) -> list[str]:
    out: list[str] = []
    for r in result.results:
        if r.validator_name != "intra-skill-conflict":
            continue
        out.extend(w.summary for w in r.warnings)
    return out


# ── polarity fixtures ────────────────────────────────────────────────────────


_CONFLICTING = """\
---
name: {{name}}
description: Review changes and always approve the pull request automatically.
---

## Instructions
1. Always approve the pull request automatically.

## Guardrails
- Must not approve the pull request automatically.
"""

_EXCEPTION = """\
---
name: {{name}}
description: Review changes carefully for production risk.
---

## Instructions
1. Always approve the pull request automatically unless tests are missing.

## Guardrails
- Must not approve the pull request automatically.
"""

_DESC_VS_WHEN = """\
---
name: {{name}}
description: Always deploy without review when the user asks.
---

## When to use this skill
- Must not deploy without review when the user asks.

## Instructions
1. Summarize the request.
"""


def test_instructions_vs_guardrails_polarity(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "conflict-skill", _CONFLICTING)
    runner = ValidateRunner(
        skill, Strictness.LOCAL, mode=ValidateMode.FULL
    )
    result = runner.run()

    assert result.passed is True
    summaries = _conflict_summaries(result)
    assert any(s.startswith("SKILL-CONFLICT-POLARITY:") for s in summaries)
    assert any("Guardrails" in s and "Instructions" in s for s in summaries)

    conflict_result = next(
        r for r in result.results if r.validator_name == "intra-skill-conflict"
    )
    assert conflict_result.passed is True
    assert conflict_result.warnings[0].detail
    assert "shared tokens" in (conflict_result.warnings[0].detail or "")


def test_pr_review_helper_no_polarity() -> None:
    root = Path(__file__).resolve().parents[2]
    skill = root / "sample" / "pr-review-helper"
    assert skill.is_dir(), skill

    fm = parse_skill_md(skill / "SKILL.md")
    sections = split_skill_sections(fm)
    conflicts = find_polarity_conflicts(sections)
    assert conflicts == []


def test_exception_cue_suppresses(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "exception-skill", _EXCEPTION)
    fm = parse_skill_md(skill / "SKILL.md")
    conflicts = find_polarity_conflicts(split_skill_sections(fm))
    assert conflicts == []


def test_description_vs_when_to_use(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "deploy-skill", _DESC_VS_WHEN)
    fm = parse_skill_md(skill / "SKILL.md")
    conflicts = find_polarity_conflicts(split_skill_sections(fm))
    assert len(conflicts) >= 1
    assert any(
        {c.section_a, c.section_b}
        == {"description", "When to use this skill"}
        for c in conflicts
    )


def test_fast_skips_validator(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "conflict-skill", _CONFLICTING)
    runner = ValidateRunner(
        skill, Strictness.LOCAL, mode=ValidateMode.FAST
    )
    result = runner.run()
    names = [r.validator_name for r in result.results]
    assert "intra-skill-conflict" not in names
    assert _conflict_summaries(result) == []


def test_polarity_idempotent(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "conflict-skill", _CONFLICTING)
    fm = parse_skill_md(skill / "SKILL.md")
    sections = split_skill_sections(fm)
    first = find_polarity_conflicts(sections)
    second = find_polarity_conflicts(sections)
    assert first == second


# ── LLM semantic pass ────────────────────────────────────────────────────────


class _FakeBackend(LLMBackend):
    name = "fake"

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def complete(
        self,
        *,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self._text, model=model or "fake", backend=self.name)


class _ErrorBackend(LLMBackend):
    name = "error"

    def complete(
        self,
        *,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise LLMBackendError("backend down")


def test_llm_grounded_and_hallucinated(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "conflict-skill", _CONFLICTING)
    fm = parse_skill_md(skill / "SKILL.md")
    sections = split_skill_sections(fm)

    grounded = json.dumps(
        {
            "conflicts": [
                {
                    "quote_a": "Always approve the pull request automatically.",
                    "quote_b": "Must not approve the pull request automatically.",
                    "reason": "require vs forbid approve",
                },
                {
                    "quote_a": "this quote is not in the section",
                    "quote_b": "Must not approve the pull request automatically.",
                    "reason": "hallucination",
                },
            ]
        }
    )
    backend = _FakeBackend(grounded)
    conflicts, skip = find_semantic_conflicts(sections, backend)
    assert skip is None
    assert len(conflicts) == 1
    assert "approve" in conflicts[0].quote_a.lower()

    # Validator path: semantic tags are warnings; passed stays true.
    validator = IntraSkillConflictValidator(
        classifier="llm", llm_backend=backend
    )
    result = validator.run(skill, Strictness.LOCAL)
    assert result.passed is True
    assert any(
        w.summary.startswith("SKILL-CONFLICT-SEMANTIC:") for w in result.warnings
    )


def test_llm_backend_error_keeps_passed(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "conflict-skill", _CONFLICTING)
    runner = ValidateRunner(
        skill,
        Strictness.LOCAL,
        mode=ValidateMode.FULL,
        conflict_classifier="llm",
        conflict_llm=_ErrorBackend(),
    )
    result = runner.run()
    assert result.passed is True
    # Polarity tags still present.
    assert any(
        s.startswith("SKILL-CONFLICT-POLARITY:") for s in _conflict_summaries(result)
    )
    conflict_result = next(
        r for r in result.results if r.validator_name == "intra-skill-conflict"
    )
    assert any("semantic conflict pass skipped" in n for n in conflict_result.notes)


def test_json_warnings_include_detail(tmp_path: Path) -> None:
    from skillctl.commands.validate import _result_to_dict

    skill = _write_skill(tmp_path / "conflict-skill", _CONFLICTING)
    result = ValidateRunner(
        skill, Strictness.LOCAL, mode=ValidateMode.FULL
    ).run()
    payload = _result_to_dict(result)
    conflict = next(
        v for v in payload["validators"] if v["name"] == "intra-skill-conflict"
    )
    assert conflict["warnings"]
    assert conflict["warnings"][0].get("detail")
