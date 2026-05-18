"""The compile pipeline core.

`CompileStep` is the strategy interface. `CompilePipeline` is the orchestrator.
`CompileContext` is the bag of shared state. Adding a new step (spec-lint,
dependency-audit, reference-freshness, codegen) is a matter of subclassing
CompileStep and registering it via the factory.

Phase 1 wires three steps: ParseFrontmatterStep, ValidateAgentSkillsSpecStep,
EmitReportStep. Phase 2 adds SpecLintStep, DependencyAuditStep,
ReferenceFreshnessStep. The pipeline shape does not change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from skillctl.agentskills import SkillFrontmatter
from skillctl.messaging import FrameworkError
from skillctl.strictness import Strictness

from .reporter import NullReporter, Reporter


class StepOutcome(str, Enum):
    """Outcome of a single compile step."""

    OK = "ok"
    WARNED = "warned"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of one CompileStep.run()."""

    step_name: str
    outcome: StepOutcome
    duration_ms: int = 0
    warnings: list[FrameworkError] = field(default_factory=list)
    errors: list[FrameworkError] = field(default_factory=list)
    # Free-form payload the step contributes to the compile report.
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompileContext:
    """Shared state passed through every CompileStep.run() invocation.

    Steps may read and mutate this. The pipeline guarantees ordering, so a
    downstream step can depend on an upstream step's contributions.
    """

    skill_dir: Path
    strictness: Strictness
    reporter: Reporter
    # Populated by ParseFrontmatterStep.
    frontmatter: SkillFrontmatter | None = None
    # Accumulated step results, in execution order.
    step_results: list[StepResult] = field(default_factory=list)
    # Where artifacts (dist/) get written.
    output_dir: Path | None = None


@dataclass
class CompileResult:
    """Final result of a CompilePipeline.run()."""

    success: bool
    skill_dir: Path
    strictness: Strictness
    step_results: list[StepResult]

    @property
    def total_warnings(self) -> int:
        return sum(len(r.warnings) for r in self.step_results)

    @property
    def total_errors(self) -> int:
        return sum(len(r.errors) for r in self.step_results)


class CompileStep(ABC):
    """Strategy interface for one step in the compile pipeline.

    Subclasses override `name`, `run`, and optionally `applies_to`.

    Steps should be small, single-purpose, and explicit about what they
    contribute to CompileContext. The pipeline is the only thing that knows
    about ordering and global control flow.
    """

    #: Human-readable name. Shown in reports and error messages.
    name: str = "anonymous-step"

    def applies_to(self, context: CompileContext) -> bool:
        """Return False to skip this step for the given context.

        Default: always run. Override for strictness-gated steps (e.g. a
        registry-context trigger validator only runs at `org`+).
        """
        return True

    @abstractmethod
    def run(self, context: CompileContext) -> StepResult:
        """Execute the step against the context.

        Must return a StepResult. Must not raise for user errors — instead,
        return a StepResult with outcome=FAILED and the errors populated.
        Bare exceptions are reserved for framework bugs.
        """


class CompilePipeline:
    """Orchestrates an ordered list of CompileSteps.

    A pipeline is configured by the factory (compile/factory.py) for a given
    strictness level. The pipeline does not know which steps are present; it
    only knows how to run them, accumulate results, and decide overall success.

    The pipeline is fail-soft: a FAILED step records the error and continues to
    the next step (so the user sees as many errors as possible per run). The
    final CompileResult.success is False if any step failed.

    A step can opt out via applies_to() — useful for strictness-gated steps.
    """

    def __init__(self, steps: list[CompileStep]):
        self._steps = list(steps)

    def run(self, context: CompileContext) -> CompileResult:
        for step in self._steps:
            if not step.applies_to(context):
                result = StepResult(step_name=step.name, outcome=StepOutcome.SKIPPED)
                context.step_results.append(result)
                context.reporter.on_step(step.name, result)
                continue

            try:
                result = step.run(context)
            except Exception as exc:  # noqa: BLE001 — framework-level safety net
                # A bare exception is a framework bug, not a user error.
                # Record it as a FAILED step with a structured message.
                result = StepResult(
                    step_name=step.name,
                    outcome=StepOutcome.FAILED,
                    errors=[
                        FrameworkError(
                            summary=f"internal error in compile step `{step.name}`",
                            detail=f"{type(exc).__name__}: {exc}",
                            fix=(
                                "This is a framework bug, not a user error. "
                                "Please open an issue with the SKILL.md and the "
                                "full output of `skillctl compile -v`."
                            ),
                        )
                    ],
                )
            context.step_results.append(result)
            context.reporter.on_step(step.name, result)

        success = not any(r.outcome == StepOutcome.FAILED for r in context.step_results)
        compile_result = CompileResult(
            success=success,
            skill_dir=context.skill_dir,
            strictness=context.strictness,
            step_results=list(context.step_results),
        )
        context.reporter.on_finish(compile_result)
        return compile_result


__all__ = [
    "CompileContext",
    "CompilePipeline",
    "CompileResult",
    "CompileStep",
    "StepOutcome",
    "StepResult",
]
