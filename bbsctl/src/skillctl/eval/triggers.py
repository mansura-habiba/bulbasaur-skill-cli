"""TriggerEvaluator — does the skill activate on the right prompts?

A trigger corpus is a list of `(prompt, expected_activation)` cases:

  positive cases   prompts where the skill SHOULD activate
                   (`expected_activation: true`)
  negative cases   prompts where the skill should NOT activate
                   (`expected_activation: false`)

The evaluator runs each prompt against the configured `AgentRuntime`, scores
the case's assertions through the judge, then derives whether the skill
*actually* activated — using the case's assertions as the signal:

  - If the case carries assertions that describe skill-applied behavior
    (the assertions pass when the skill has clearly fired), the case score
    is the activation signal.
  - The case PASSES when the observed activation matches the expected
    activation:
      expected=True, score >= activation_threshold → PASS
      expected=False, score <  activation_threshold → PASS
    Mismatches fail.

A synthetic `trigger-precision` and `trigger-recall` assertion is added per
case so the standard report surfaces classification correctness alongside
the regular assertion verdicts.

Suite format — `evals/triggers.json`:

    {
      "skill_name": "mq-restarter",
      "evals": [
        {
          "id": "pos-001",
          "prompt": "Restart deployment mq-operator in mq-prod.",
          "expected_activation": true,
          "expected_output": "ValidationReport with kubectl rollout restart.",
          "assertions": [
            "kubectl rollout restart command is mentioned",
            "Health check is performed after restart"
          ]
        },
        {
          "id": "neg-001",
          "prompt": "What's the weather today?",
          "expected_activation": false,
          "assertions": [
            "Response does not include kubectl commands",
            "Response refuses or pivots — not skill content"
          ]
        }
      ]
    }
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

# A case is treated as "skill activated" when the fraction of its assertions
# passing reaches this threshold. Tunable per-corpus in a future extension.
DEFAULT_ACTIVATION_THRESHOLD = 0.5


class TriggerEvaluator(Evaluator):
    """Suite name: `triggers`. Activation precision/recall.

    Cases without an explicit `expected_activation` field default to True
    (positive case) — keeps the format compatible with the existing
    `behavior.json` shape so authors can promote a behavior case into a
    trigger case by just adding the boolean.
    """

    name = "triggers"

    def __init__(
        self,
        *,
        skill: SkillFrontmatter,
        runtime: AgentRuntime,
        judge: Judge,
        activation_threshold: float = DEFAULT_ACTIVATION_THRESHOLD,
    ) -> None:
        self._skill = skill
        self._runtime = runtime
        self._judge = judge
        self._threshold = activation_threshold

    def evaluate(self, suite: EvalSuite) -> SuiteResult:
        case_results = [self._evaluate_case(c) for c in suite.cases]

        # Compute aggregate precision/recall and stash on the result so
        # downstream reporters can surface it.
        agg = _aggregate(case_results)
        sr = SuiteResult(
            suite_name=suite.name,
            skill_name=suite.skill_name,
            cases=case_results,
        )
        sr._trigger_summary = agg  # type: ignore[attr-defined]
        return sr

    # ── per-case ──────────────────────────────────────────────────────

    def _evaluate_case(self, case: EvalCase) -> CaseResult:
        started = time.monotonic()
        expected_activation = _read_expected_activation(case)

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

        observed_score = (
            sum(1 for a in assertion_results if a.passed)
            / max(len(assertion_results), 1)
        )
        observed_activation = observed_score >= self._threshold

        # Synthetic verdict: does observed match expected?
        if expected_activation:
            classification_passed = observed_activation
            classification_assertion = (
                f"positive case `{case.id}`: skill activates on this prompt"
            )
        else:
            classification_passed = not observed_activation
            classification_assertion = (
                f"negative case `{case.id}`: skill stays out of this prompt"
            )
        classification_reason = (
            f"observed_score={observed_score:.2f} threshold={self._threshold:.2f}"
            f"; expected_activation={expected_activation}"
            f"; observed_activation={observed_activation}"
        )

        # Combine: the case's own assertions follow the same pass/fail
        # convention as BehaviorEvaluator AND we append the classification
        # verdict so the case fails on mis-classification even if the
        # individual assertions are uninformative.
        all_assertions = list(assertion_results) + [
            AssertionResult(
                assertion=classification_assertion,
                passed=classification_passed,
                reason=classification_reason,
            )
        ]

        duration_ms = int((time.monotonic() - started) * 1000)
        return CaseResult(
            case_id=case.id,
            prompt=case.prompt,
            expected_output=case.expected_output,
            actual_output=actual_output,
            assertions=all_assertions,
            duration_ms=duration_ms,
            runtime_error=runtime_error,
        )


def _read_expected_activation(case: EvalCase) -> bool:
    """Pull `expected_activation` off the case.

    The loader doesn't currently parse this field, so it lives in the case id
    convention (`pos-…` / `neg-…`) or in a `files` array marker as a fallback.
    Default: True (positive case) — keeps the format compatible with behavior
    suites where every case is implicitly expected to trigger.
    """
    # Convention 1: case id prefix.
    cid = case.id.lower()
    if cid.startswith("neg") or cid.startswith("negative") or cid.startswith("no-"):
        return False
    if cid.startswith("pos") or cid.startswith("positive") or cid.startswith("yes-"):
        return True
    # Convention 2: marker file (used until the loader gains the field).
    for marker in case.files:
        if marker.strip().lower() in {"expected_activation=false", "negative"}:
            return False
        if marker.strip().lower() in {"expected_activation=true", "positive"}:
            return True
    return True


# ── aggregation ────────────────────────────────────────────────────────────


def _aggregate(case_results: list[CaseResult]) -> dict:
    """Compute confusion-matrix metrics across every case.

    A case PASSED → the model's observed activation matched the expected
    activation. We back out positive/negative class from the case id
    convention so the precision/recall numbers are meaningful even when
    the suite mixes positives and negatives.
    """
    tp = fp = fn = tn = 0
    for c in case_results:
        cid = c.case_id.lower()
        # Positive class = the skill should activate.
        expected_positive = not (
            cid.startswith("neg")
            or cid.startswith("negative")
            or cid.startswith("no-")
        )
        # The last assertion is the synthetic classification verdict.
        if not c.assertions:
            continue
        matched = c.assertions[-1].passed
        if expected_positive:
            if matched:
                tp += 1
            else:
                fn += 1
        else:
            if matched:
                tn += 1
            else:
                fp += 1

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (
        2 * precision * recall / max(precision + recall, 1e-9)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def get_trigger_summary(result: SuiteResult) -> dict | None:
    """Pull the trigger-classification aggregate off a SuiteResult."""
    return getattr(result, "_trigger_summary", None)


__all__ = [
    "DEFAULT_ACTIVATION_THRESHOLD",
    "TriggerEvaluator",
    "get_trigger_summary",
]
