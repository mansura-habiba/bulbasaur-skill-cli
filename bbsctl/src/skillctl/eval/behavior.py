"""BehaviorEvaluator — the default evaluator for `evals/behavior.json`.

Two-stage pipeline per case:

1. Activate the skill against the case prompt using an AgentRuntime adapter.
   In Phase 1 the only adapter is MockAgent; real adapters land in Phase 4.
2. For each assertion, ask the configured Judge to score it against the
   actual output. Aggregate per-case and per-suite.

This evaluator does not care which runtime or judge is in use — both are
injected, which keeps the unit tests fast (mock runtime + heuristic judge)
and makes Phase 4 a drop-in swap (real runtime + LLM judge).
"""

from __future__ import annotations

import time

from skillctl.agentskills import SkillFrontmatter
from skillctl.run.runtime import AgentRuntime

from .base import (
    AssertionResult,
    CaseResult,
    EvalCase,
    EvalSuite,
    Evaluator,
    SuiteResult,
)
from .judge import Judge


class BehaviorEvaluator(Evaluator):
    """Default evaluator. Suite name: `behavior`.

    Also runs as the fallback for any suite whose name is not specifically
    registered (e.g. user-defined custom suite files).
    """

    name = "behavior"

    def __init__(
        self,
        *,
        skill: SkillFrontmatter,
        runtime: AgentRuntime,
        judge: Judge,
    ) -> None:
        self._skill = skill
        self._runtime = runtime
        self._judge = judge

    def evaluate(self, suite: EvalSuite) -> SuiteResult:
        case_results = [self._evaluate_case(c) for c in suite.cases]
        return SuiteResult(
            suite_name=suite.name,
            skill_name=suite.skill_name,
            cases=case_results,
        )

    def _evaluate_case(self, case: EvalCase) -> CaseResult:
        started = time.monotonic()

        try:
            response = self._runtime.activate(self._skill, case.prompt)
            actual_output = response.reply
            runtime_error: str | None = None
        except Exception as exc:
            # Runtime failures are case-level, not framework-level.
            actual_output = ""
            runtime_error = f"{type(exc).__name__}: {exc}"

        assertion_results: list[AssertionResult] = []
        if runtime_error is None:
            for assertion in case.assertions:
                verdict = self._judge.score(
                    assertion=assertion,
                    actual_output=actual_output,
                    expected_output=case.expected_output,
                )
                assertion_results.append(
                    AssertionResult(
                        assertion=assertion,
                        passed=verdict.passed,
                        reason=verdict.reason,
                    )
                )

        duration_ms = int((time.monotonic() - started) * 1000)

        return CaseResult(
            case_id=case.id,
            prompt=case.prompt,
            expected_output=case.expected_output,
            actual_output=actual_output,
            assertions=assertion_results,
            duration_ms=duration_ms,
            runtime_error=runtime_error,
        )


__all__ = ["BehaviorEvaluator"]
