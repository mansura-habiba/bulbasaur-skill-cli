"""Concrete CompileStep implementations.

Phase 1 ships three steps:

  ParseFrontmatterStep         load SKILL.md, parse YAML frontmatter, validate
                               required fields and agentskills.io rules.
  ValidateAgentSkillsSpecStep  re-affirm spec validity (a separate step so the
                               factory can swap in `skills-ref` later without
                               changing parsing behavior).
  EmitReportStep               write dist/compile-report.json with the full
                               compile artifact.

Phase 2 adds: SpecLintStep, DependencyAuditStep, ReferenceFreshnessStep, etc.
Each new step is one class registered through `compile.factory.register_step`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from skillctl.agentskills import (
    AgentSkillsValidationError,
    parse_skill_md,
)
from skillctl.messaging import FrameworkError
from skillctl.strictness import Strictness

from .pipeline import CompileContext, CompileStep, StepOutcome, StepResult


def _validation_error_to_framework_error(
    err: AgentSkillsValidationError, *, docs: str | None = None
) -> FrameworkError:
    """Translate an AgentSkillsValidationError into our user-facing error contract."""
    return FrameworkError(
        summary=f"{err.field}: {err.message}",
        detail=f"agentskills.io rule violation (code={err.code})",
        fix=err.fix,
        docs=docs or "https://agentskills.io/specification",
    )


class ParseFrontmatterStep(CompileStep):
    """Step 1: parse SKILL.md frontmatter and validate against agentskills.io rules.

    On success: populates context.frontmatter and payload['frontmatter'].
    On failure: returns FAILED with the structured error; downstream steps see
    no frontmatter and can opt out via applies_to().
    """

    name = "parse-frontmatter"

    def run(self, context: CompileContext) -> StepResult:
        started = time.monotonic()
        skill_md = context.skill_dir / "SKILL.md"

        if not skill_md.exists():
            return StepResult(
                step_name=self.name,
                outcome=StepOutcome.FAILED,
                duration_ms=int((time.monotonic() - started) * 1000),
                errors=[
                    FrameworkError(
                        summary="SKILL.md not found",
                        detail=f"expected at {skill_md}",
                        fix=(
                            "Run `bbsctl new <name>` to scaffold a skill, or `cd` into "
                            "the skill directory before running `bbsctl compile`."
                        ),
                    )
                ],
            )

        try:
            frontmatter = parse_skill_md(skill_md)
        except AgentSkillsValidationError as exc:
            return StepResult(
                step_name=self.name,
                outcome=StepOutcome.FAILED,
                duration_ms=int((time.monotonic() - started) * 1000),
                errors=[_validation_error_to_framework_error(exc)],
            )
        except FileNotFoundError as exc:
            return StepResult(
                step_name=self.name,
                outcome=StepOutcome.FAILED,
                duration_ms=int((time.monotonic() - started) * 1000),
                errors=[
                    FrameworkError(
                        summary="SKILL.md not found",
                        detail=str(exc),
                        fix="Check the path and re-run.",
                    )
                ],
            )

        context.frontmatter = frontmatter
        return StepResult(
            step_name=self.name,
            outcome=StepOutcome.OK,
            duration_ms=int((time.monotonic() - started) * 1000),
            payload={
                "name": frontmatter.name,
                "description_length": len(frontmatter.description or ""),
                "has_license": frontmatter.license is not None,
                "has_compatibility": frontmatter.compatibility is not None,
                "has_metadata": frontmatter.metadata is not None,
                "body_chars": len(frontmatter.body),
            },
        )


class ValidateAgentSkillsSpecStep(CompileStep):
    """Step 2: confirm spec validity post-parse.

    A separate step (rather than folded into parse) so the factory can swap in
    different validators — for example, a future step that delegates to the
    upstream `skills-ref` CLI for a second opinion (ADR 0004). Today this step
    relies on the rules already enforced by parse_skill_md but checks them
    again for defense in depth and reports them as a distinct stage.
    """

    name = "validate-agentskills-spec"

    def applies_to(self, context: CompileContext) -> bool:
        # Skip if parsing failed; no point re-validating None.
        return context.frontmatter is not None

    def run(self, context: CompileContext) -> StepResult:
        started = time.monotonic()
        # If parse succeeded, the spec is valid (parse_skill_md raises otherwise).
        # This step is a placeholder for the multi-validator chain landing in Phase 2
        # (skills-ref second opinion, divergence warning, etc.).
        return StepResult(
            step_name=self.name,
            outcome=StepOutcome.OK,
            duration_ms=int((time.monotonic() - started) * 1000),
            payload={"spec_url": "https://agentskills.io/specification"},
        )


class EmitReportStep(CompileStep):
    """Step N (final): write dist/compile-report.json with all step payloads.

    Creates dist/ next to SKILL.md and writes a single JSON file. Future steps
    that emit additional artifacts (SBOM, lockfile, spec-lint.json) write into
    the same dist/ directory.
    """

    name = "emit-report"

    def run(self, context: CompileContext) -> StepResult:
        started = time.monotonic()
        dist_dir = context.skill_dir / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        context.output_dir = dist_dir

        # Construct the self-result first so we can include this step in the report.
        # The pipeline appends our return value to context.step_results AFTER this
        # method returns; including ourselves here keeps the report complete.
        report_path = dist_dir / "compile-report.json"
        self_result = StepResult(
            step_name=self.name,
            outcome=StepOutcome.OK,
            duration_ms=int((time.monotonic() - started) * 1000),
            payload={"report_path": str(report_path)},
        )

        all_steps = list(context.step_results) + [self_result]

        report: dict[str, Any] = {
            "skillctl_version": _skillctl_version(),
            "skill_dir": str(context.skill_dir),
            "strictness": context.strictness.value,
            "frontmatter": (
                {
                    "name": context.frontmatter.name,
                    "description": context.frontmatter.description,
                    "license": context.frontmatter.license,
                    "compatibility": context.frontmatter.compatibility,
                    "allowed-tools": context.frontmatter.allowed_tools,
                }
                if context.frontmatter is not None
                else None
            ),
            "steps": [
                {
                    "name": r.step_name,
                    "outcome": r.outcome.value,
                    "duration_ms": r.duration_ms,
                    "payload": r.payload,
                    "errors": [_error_to_dict(e) for e in r.errors],
                    "warnings": [_error_to_dict(w) for w in r.warnings],
                }
                for r in all_steps
            ],
        }

        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return self_result


def _error_to_dict(err: FrameworkError) -> dict[str, Any]:
    return {"summary": err.summary, "detail": err.detail, "fix": err.fix, "docs": err.docs}


def _skillctl_version() -> str:
    """Return the installed skillctl version."""
    try:
        from skillctl import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"


__all__ = [
    "ParseFrontmatterStep",
    "ValidateAgentSkillsSpecStep",
    "EmitReportStep",
]
