"""A/B baseline testing — does the skill actually help?

Inspired by `waza run --baseline`. For each case, activate the skill twice:

  1. WITH the skill body as system prompt (the normal run)
  2. WITHOUT the skill body (an empty SkillFrontmatter) — baseline

Score both. Compute the delta. Report per-case improvement and suite-level
pass-rate lift. A skill whose `with_skill` score isn't materially better than
`without_skill` may not be earning its context budget.

The wrapper pattern keeps this composable: `BaselineEvaluator` takes another
`Evaluator` and runs it twice per case, on the same prompts, against the same
judge. The wrapped evaluator can be `BehaviorEvaluator`, `TriggerEvaluator`,
`InjectionEvaluator`, or `SemanticFuzzer` — any of them benefits from the A/B
comparison.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

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


@dataclass
class BaselineCaseDelta:
    """Per-case improvement summary attached to the case payload."""

    case_id: str
    with_skill_score: float
    without_skill_score: float
    delta: float
    with_skill_passed: bool
    without_skill_passed: bool

    @property
    def helped(self) -> bool:
        """True when adding the skill strictly improved the score."""
        return self.delta > 0

    @property
    def hurt(self) -> bool:
        """True when adding the skill made the score worse."""
        return self.delta < 0


@dataclass
class BaselineSuiteSummary:
    """Suite-level aggregate of the A/B run."""

    pass_rate_with_skill: float
    pass_rate_without_skill: float
    mean_score_with_skill: float
    mean_score_without_skill: float
    score_delta: float                 # mean_with - mean_without
    pass_rate_delta: float             # pass_rate_with - pass_rate_without
    cases_helped: int = 0
    cases_hurt: int = 0
    cases_unchanged: int = 0
    deltas: list[BaselineCaseDelta] = field(default_factory=list)


class BaselineEvaluator(Evaluator):
    """A/B wrapper around another evaluator.

    For each case, runs the inner evaluator twice — once with the real skill,
    once with an empty skill. Aggregates the deltas into a
    `BaselineSuiteSummary` stashed on the returned SuiteResult's first case
    payload metadata.

    The wrapper exists so any Evaluator can be A/B'd without changing the
    evaluator's contract. Construction:

        inner = BehaviorEvaluator(skill=skill, runtime=runtime, judge=judge)
        baseline = BaselineEvaluator(
            skill=skill, runtime=runtime, judge=judge, inner=inner,
        )
    """

    name = "baseline"

    def __init__(
        self,
        *,
        skill: SkillFrontmatter,
        runtime: AgentRuntime,
        judge: Judge,
        inner: Evaluator | None = None,
    ) -> None:
        self._skill = skill
        self._runtime = runtime
        self._judge = judge
        # Default inner is BehaviorEvaluator — most common A/B target.
        if inner is None:
            from .behavior import BehaviorEvaluator

            inner = BehaviorEvaluator(
                skill=skill, runtime=runtime, judge=judge
            )
        self._inner = inner

    def evaluate(self, suite: EvalSuite) -> SuiteResult:
        # Run the inner evaluator with the real skill — the normal path.
        with_suite = self._inner.evaluate(suite)

        # Build an empty-skill twin so the second pass is identical in
        # every respect except the system prompt content.
        empty_skill = _empty_skill_like(self._skill)
        # Use a parallel inner evaluator with the empty skill so all the
        # inner's assertion + judge logic runs identically.
        twin_inner = _swap_skill(self._inner, empty_skill)
        without_suite = twin_inner.evaluate(suite)

        deltas: list[BaselineCaseDelta] = []
        helped = hurt = unchanged = 0
        with_pass = without_pass = 0
        score_with_sum = score_without_sum = 0.0

        for w_case, wo_case in zip(with_suite.cases, without_suite.cases):
            delta = BaselineCaseDelta(
                case_id=w_case.case_id,
                with_skill_score=w_case.score,
                without_skill_score=wo_case.score,
                delta=round(w_case.score - wo_case.score, 6),
                with_skill_passed=w_case.passed,
                without_skill_passed=wo_case.passed,
            )
            deltas.append(delta)
            if delta.helped:
                helped += 1
            elif delta.hurt:
                hurt += 1
            else:
                unchanged += 1
            if w_case.passed:
                with_pass += 1
            if wo_case.passed:
                without_pass += 1
            score_with_sum += w_case.score
            score_without_sum += wo_case.score

        n = max(len(with_suite.cases), 1)
        summary = BaselineSuiteSummary(
            pass_rate_with_skill=with_pass / n,
            pass_rate_without_skill=without_pass / n,
            mean_score_with_skill=score_with_sum / n,
            mean_score_without_skill=score_without_sum / n,
            score_delta=round((score_with_sum - score_without_sum) / n, 6),
            pass_rate_delta=round((with_pass - without_pass) / n, 6),
            cases_helped=helped,
            cases_hurt=hurt,
            cases_unchanged=unchanged,
            deltas=deltas,
        )

        # Decorate every case with the per-case A/B context as a synthetic
        # assertion so the standard reporter surfaces it without changes.
        annotated_cases: list[CaseResult] = []
        for w_case, delta in zip(with_suite.cases, deltas):
            ab_assertion = AssertionResult(
                assertion=f"baseline: skill helped on case `{w_case.case_id}`",
                passed=delta.helped or (delta.with_skill_passed and not delta.helped),
                reason=(
                    f"with_skill={delta.with_skill_score:.2f} "
                    f"vs without_skill={delta.without_skill_score:.2f} "
                    f"(delta={delta.delta:+.2f})"
                ),
            )
            annotated_cases.append(
                CaseResult(
                    case_id=w_case.case_id,
                    prompt=w_case.prompt,
                    expected_output=w_case.expected_output,
                    actual_output=w_case.actual_output,
                    assertions=list(w_case.assertions) + [ab_assertion],
                    duration_ms=w_case.duration_ms,
                    runtime_error=w_case.runtime_error,
                )
            )

        result = SuiteResult(
            suite_name=f"{with_suite.suite_name}+baseline",
            skill_name=with_suite.skill_name,
            cases=annotated_cases,
        )
        # Stash the structured summary so machine-readable reports can pick
        # it up. Reporters consult `_baseline_summary` on the SuiteResult.
        result._baseline_summary = summary  # type: ignore[attr-defined]
        return result


# ── helpers ────────────────────────────────────────────────────────────────


def _empty_skill_like(skill: SkillFrontmatter) -> SkillFrontmatter:
    """Build a SkillFrontmatter with the same name/version metadata but no body.

    Some runtimes use the skill `name` for trace labelling; preserve it so
    the trace still attributes correctly while the *content* is empty.
    """
    return SkillFrontmatter(
        raw_frontmatter={
            "name": (skill.name or "baseline") + ":no-skill",
            "description": "",
        },
        body="",
        body_line_offset=4,
    )


def _swap_skill(inner: Evaluator, replacement: SkillFrontmatter) -> Evaluator:
    """Return an evaluator like `inner` but bound to `replacement` skill.

    The four shipped evaluators (Behavior, Trigger, Injection, Fuzz) all hold
    the skill on `_skill`. We construct a new instance of the same class with
    the replacement skill so the inner's runtime/judge/state are preserved.
    """
    klass = type(inner)
    # Every inner takes (skill, runtime, judge) as kwargs; some take
    # additional kwargs we want to preserve.
    init_kwargs: dict = {
        "skill": replacement,
        "runtime": getattr(inner, "_runtime"),
        "judge": getattr(inner, "_judge"),
    }
    # SemanticFuzzer carries a backend + n_variants — preserve those.
    if hasattr(inner, "_backend") and hasattr(inner, "_n_variants"):
        init_kwargs["backend"] = getattr(inner, "_backend")
        init_kwargs["n_variants"] = getattr(inner, "_n_variants")
    return klass(**init_kwargs)


def get_baseline_summary(result: SuiteResult) -> BaselineSuiteSummary | None:
    """Pull the structured A/B summary off a SuiteResult, if present."""
    return getattr(result, "_baseline_summary", None)


__all__ = [
    "BaselineCaseDelta",
    "BaselineEvaluator",
    "BaselineSuiteSummary",
    "get_baseline_summary",
]
