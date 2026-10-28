"""IntraSkillConflictValidator — tag contradictions across SKILL.md sections.

Runs only under ``ValidateMode.FULL``. Conflict tags are warnings; ``passed``
stays true unless a hard parse failure is treated as skip (still passed).
"""

from __future__ import annotations

import time
from pathlib import Path

from skillctl.agentskills.frontmatter import parse_skill_md
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.agentskills.sections import split_skill_sections
from skillctl.analyze.polarity import PolarityConflict, find_polarity_conflicts
from skillctl.analyze.semantic import find_semantic_conflicts
from skillctl.messaging import FrameworkError
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult


class IntraSkillConflictValidator(Validator):
    """Tag polarity (and optional LLM) conflicts inside one SKILL.md."""

    name = "intra-skill-conflict"

    def __init__(
        self,
        *,
        classifier: str = "heuristic",
        backend: str | None = None,
        model: str | None = None,
        llm_backend: object | None = None,
    ) -> None:
        self._classifier = classifier
        self._backend_name = backend
        self._model = model
        # Injected backend for tests; when set, skips build_backend.
        self._llm_backend = llm_backend

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            notes.append("SKILL.md not found; skipping conflict check")
            return self._result(started, warnings, notes)

        try:
            fm = parse_skill_md(skill_md)
        except (AgentSkillsValidationError, OSError, FileNotFoundError) as exc:
            notes.append(f"Could not parse SKILL.md; skipping conflict check ({exc})")
            return self._result(started, warnings, notes)

        sections = split_skill_sections(fm)
        if len(sections) < 2:
            notes.append("fewer than two authored sections; no conflict pairs")
            return self._result(started, warnings, notes)

        polarity = find_polarity_conflicts(sections)
        for conflict in polarity:
            warnings.append(_polarity_warning(conflict))

        notes.append(
            f"polarity: {len(polarity)} conflict(s) across {len(sections)} section(s)"
        )

        if self._classifier == "llm":
            semantic_warnings, skip_note = self._run_semantic(sections)
            warnings.extend(semantic_warnings)
            if skip_note:
                notes.append(skip_note)
            else:
                notes.append(f"semantic: {len(semantic_warnings)} conflict(s)")

        return self._result(started, warnings, notes)

    def _run_semantic(
        self, sections: list
    ) -> tuple[list[FrameworkError], str | None]:
        backend = self._llm_backend
        if backend is None:
            try:
                from skillctl.llm import build_backend

                backend = build_backend(self._backend_name)
            except Exception as exc:
                return [], f"semantic conflict pass skipped: {exc}"

        conflicts, skip_note = find_semantic_conflicts(
            sections, backend, model=self._model  # type: ignore[arg-type]
        )
        warnings = [_semantic_warning(c) for c in conflicts]
        return warnings, skip_note

    def _result(
        self,
        started: float,
        warnings: list[FrameworkError],
        notes: list[str],
    ) -> ValidatorResult:
        return ValidatorResult(
            validator_name=self.name,
            passed=True,
            duration_ms=int((time.monotonic() - started) * 1000),
            warnings=warnings,
            notes=notes,
        )


def _polarity_warning(conflict: PolarityConflict) -> FrameworkError:
    shared = ", ".join(conflict.shared_tokens)
    return FrameworkError(
        summary=(
            f"SKILL-CONFLICT-POLARITY: {conflict.section_a} vs {conflict.section_b}"
        ),
        detail=(
            f"L{conflict.line_a}: {conflict.quote_a!r} "
            f"conflicts with L{conflict.line_b}: {conflict.quote_b!r} "
            f"(shared tokens: {shared})"
        ),
        fix=(
            f"Rewrite one statement in {conflict.section_a} or {conflict.section_b} "
            "so the polarities agree for the same action."
        ),
    )


def _semantic_warning(conflict) -> FrameworkError:
    return FrameworkError(
        summary=(
            f"SKILL-CONFLICT-SEMANTIC: {conflict.section_a} vs {conflict.section_b}"
        ),
        detail=(
            f"{conflict.quote_a!r} vs {conflict.quote_b!r} — {conflict.reason}"
        ),
        fix=(
            f"Reconcile the opposing guidance in {conflict.section_a} and "
            f"{conflict.section_b}."
        ),
    )


__all__ = ["IntraSkillConflictValidator"]
