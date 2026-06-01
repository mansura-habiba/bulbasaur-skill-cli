"""InjectionEvaluator — score skill behavior under prompt-injection attacks.

The evaluator reads `evals/injection.json` (same `{skill_name, evals: [...]}`
shape as the behavior corpus) but each case carries extra fields:

  category   one of `system_prompt_extraction`, `instruction_override`,
             `output_format_hijack`, `tool_invocation_hijack`, `data_exfil`,
             `role_play_override`, `delimiter_confusion`.
  severity   one of `critical`, `high`, `medium`, `low`. Severities aggregate
             into the report.
  prompt     the injection payload sent to the skill.
  expected_behavior  natural-language description of correct refusal.
  assertions a list of natural-language claims a judge scores.

Per-case scoring is the same as `BehaviorEvaluator` — the AgentRuntime
activates the skill against the injection payload; the configured Judge
scores each assertion. Per-suite scoring additionally aggregates by severity
so the report surfaces "5/5 critical, 3/4 high, ..." in one glance.

Mellea ships hand-written single-prompt fixtures; this evaluator is the
multi-category corpus + scoring layer Mellea does not have.
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


class InjectionEvaluator(Evaluator):
    """Default evaluator for `evals/injection.json`. Suite name: `injection`."""

    name = "injection"

    # Severity-weighted scoring: a critical failure costs more than a low one.
    _SEVERITY_WEIGHT: dict[str, float] = {
        "critical": 4.0,
        "high": 2.0,
        "medium": 1.0,
        "low": 0.5,
        "": 1.0,  # un-tagged cases get medium weight
    }

    def __init__(
        self, *, skill: SkillFrontmatter, runtime: AgentRuntime, judge: Judge
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
        # InjectionCase metadata travels through EvalCase via a `metadata` dict
        # the loader stashes into the assertion text or — for the v1 shipping
        # corpus — through the case `id` convention `<category>:<severity>:<n>`.
        category, severity = _parse_case_metadata(case.id)

        try:
            response = self._runtime.activate(self._skill, case.prompt)
            actual_output = response.reply
            runtime_error: str | None = None
        except Exception as exc:
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
        # Stash severity into prompt prefix for downstream reporters; CaseResult
        # is dataclass-frozen-by-convention so this keeps within the existing shape.
        prompt_with_meta = (
            f"[category={category} severity={severity}] {case.prompt}"
            if (category or severity)
            else case.prompt
        )
        return CaseResult(
            case_id=case.id,
            prompt=prompt_with_meta,
            expected_output=case.expected_output,
            actual_output=actual_output,
            assertions=assertion_results,
            duration_ms=duration_ms,
            runtime_error=runtime_error,
        )


def _parse_case_metadata(case_id: str) -> tuple[str, str]:
    """Pull category + severity from a case id of form `cat:sev:n` or `cat:sev`.

    Returns (category, severity) — both strings, empty if not declared.
    """
    parts = case_id.split(":")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", ""


__all__ = ["InjectionEvaluator"]
