"""Factory that builds CompilePipelines from a Strictness level + config.

The factory is the only place that knows which steps to include for which
strictness level. This keeps the CompilePipeline orchestrator unaware of
strictness, and the steps unaware of each other.

Steps are registered into a global ordered registry. Phase 2 adds steps by
calling `register_step` at module import time — no changes to the factory
function itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from skillctl.strictness import Strictness

from .pipeline import CompilePipeline, CompileStep
from .steps import (
    EmitReportStep,
    ParseFrontmatterStep,
    ValidateAgentSkillsSpecStep,
)


@dataclass(frozen=True)
class StepRegistration:
    """A step registered with the factory.

    `applies_at` declares the minimum strictness at which this step is active.
    The factory builds a pipeline by filtering the registry to steps whose
    `applies_at` is satisfied by the target strictness.
    """

    factory: Callable[[], CompileStep]
    applies_at: Strictness


# Step registry, in execution order. Phase 2+ steps are appended at the bottom.
_REGISTRY: list[StepRegistration] = [
    StepRegistration(factory=ParseFrontmatterStep, applies_at=Strictness.LOCAL),
    StepRegistration(factory=ValidateAgentSkillsSpecStep, applies_at=Strictness.LOCAL),
    # EmitReportStep is intentionally last so it sees every preceding step's results.
    StepRegistration(factory=EmitReportStep, applies_at=Strictness.LOCAL),
]


def register_step(factory: Callable[[], CompileStep], *, applies_at: Strictness) -> None:
    """Register a CompileStep factory at the given minimum strictness.

    The step is appended to the registry. Steps execute in registration order.

    Phase 2 will call register_step for SpecLintStep, DependencyAuditStep,
    ReferenceFreshnessStep, etc.
    """
    _REGISTRY.append(StepRegistration(factory=factory, applies_at=applies_at))


def build_pipeline(strictness: Strictness = Strictness.LOCAL) -> CompilePipeline:
    """Build a CompilePipeline for the given strictness level.

    Includes all registered steps whose `applies_at` is at or below the target
    strictness. Steps internally may further skip via `applies_to(context)`.
    """
    steps = [r.factory() for r in _REGISTRY if strictness.includes(r.applies_at)]
    return CompilePipeline(steps=steps)


__all__ = ["build_pipeline", "register_step", "StepRegistration"]
