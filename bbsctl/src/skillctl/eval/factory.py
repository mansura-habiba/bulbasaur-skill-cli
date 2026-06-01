"""Factories for evaluators and judges.

Adding a new evaluator (e.g. TriggerEvaluator for `evals/triggers.json`) is:

    from skillctl.eval.factory import register_evaluator

    register_evaluator("triggers", lambda skill, runtime, judge: TriggerEvaluator(...))

The registry maps suite name → constructor. The runner picks a constructor
by suite name; suites without a registered evaluator fall back to
BehaviorEvaluator.

Judges follow the same pattern. `heuristic` is the default Phase 1 judge.
`llm` is reserved for the Claude Agent SDK adapter (Phase 4); calling
build_judge("llm") today raises with a clear "not wired yet" message.
"""

from __future__ import annotations

from collections.abc import Callable

from skillctl.agentskills import SkillFrontmatter
from skillctl.run.runtime import AgentRuntime

from .base import Evaluator
from .behavior import BehaviorEvaluator
from .judge import HeuristicJudge, Judge

EvaluatorFactory = Callable[[SkillFrontmatter, AgentRuntime, Judge], Evaluator]
JudgeFactory = Callable[[], Judge]


def _build_injection_evaluator(skill, runtime, judge):
    from .injection import InjectionEvaluator

    return InjectionEvaluator(skill=skill, runtime=runtime, judge=judge)


def _build_fuzz_evaluator(skill, runtime, judge):
    from .fuzzer import SemanticFuzzer

    return SemanticFuzzer(skill=skill, runtime=runtime, judge=judge)


_EVALUATOR_REGISTRY: dict[str, EvaluatorFactory] = {
    "behavior": lambda skill, runtime, judge: BehaviorEvaluator(
        skill=skill, runtime=runtime, judge=judge
    ),
    "injection": _build_injection_evaluator,
    "fuzz": _build_fuzz_evaluator,
}


def _build_llm_judge() -> Judge:
    """Lazy LLMJudge construction — imports the llm module only when needed.

    Keeps the base install dependency-light by deferring backend resolution
    until the user actually picks `--judge llm`.
    """
    from .llm_judge import LLMJudge

    return LLMJudge()


_JUDGE_REGISTRY: dict[str, JudgeFactory] = {
    "heuristic": HeuristicJudge,
    "llm": _build_llm_judge,
}


def register_evaluator(suite_name: str, factory: EvaluatorFactory) -> None:
    """Register an evaluator constructor for a suite name.

    Called at import time from modules that ship additional evaluators
    (TriggerEvaluator, InjectionEvaluator, RegressionEvaluator in Phase 3).
    """
    _EVALUATOR_REGISTRY[suite_name] = factory


def build_evaluator(
    suite_name: str,
    *,
    skill: SkillFrontmatter,
    runtime: AgentRuntime,
    judge: Judge,
) -> Evaluator:
    """Build an evaluator for a suite. Falls back to BehaviorEvaluator."""
    factory = _EVALUATOR_REGISTRY.get(suite_name) or _EVALUATOR_REGISTRY["behavior"]
    return factory(skill, runtime, judge)


def list_evaluators() -> list[str]:
    return sorted(_EVALUATOR_REGISTRY.keys())


def register_judge(name: str, factory: JudgeFactory) -> None:
    """Register a judge constructor under `name`."""
    _JUDGE_REGISTRY[name] = factory


def build_judge(name: str = "heuristic") -> Judge:
    """Build a judge by name.

    Phase 1 default: `heuristic` (deterministic, no API key).
    Phase 4: `llm` registers when the Claude Agent SDK adapter ships.
    """
    factory = _JUDGE_REGISTRY.get(name)
    if factory is None:
        available = ", ".join(sorted(_JUDGE_REGISTRY.keys()))
        raise ValueError(f"unknown judge: {name!r}. Available: {available}")
    return factory()


def list_judges() -> list[str]:
    return sorted(_JUDGE_REGISTRY.keys())


__all__ = [
    "build_evaluator",
    "build_judge",
    "list_evaluators",
    "list_judges",
    "register_evaluator",
    "register_judge",
]
