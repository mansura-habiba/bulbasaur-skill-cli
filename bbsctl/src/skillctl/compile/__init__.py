"""The compile module — turns a SKILL.md (and optional skill.yaml) into typed compile artifacts.

The pipeline is a strategy chain (per the framework's design pattern guidance):

  CompileContext           shared state passed through the pipeline
  CompileStep (ABC)        every step implements `run(context) -> StepResult`
  CompilePipeline          orchestrates steps, accumulates results, decides failure
  PipelineFactory          builds the right pipeline for a strictness level + config

Adding a new compile step (Phase 2: spec-lint, dependency-audit, reference-freshness)
is a matter of writing one CompileStep subclass and registering it with the factory.
"""

from .factory import build_pipeline, register_step
from .pipeline import (
    CompileContext,
    CompilePipeline,
    CompileResult,
    CompileStep,
    StepOutcome,
    StepResult,
)
from .reporter import JsonReporter, NullReporter, Reporter, TextReporter

__all__ = [
    "CompileContext",
    "CompilePipeline",
    "CompileResult",
    "CompileStep",
    "JsonReporter",
    "NullReporter",
    "Reporter",
    "StepOutcome",
    "StepResult",
    "TextReporter",
    "build_pipeline",
    "register_step",
]
