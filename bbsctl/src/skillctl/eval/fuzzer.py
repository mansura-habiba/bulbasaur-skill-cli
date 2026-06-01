"""SemanticFuzzer — generate rephrasings and check skill output stability.

Mellea does not ship semantic fuzzing. The fuzzer takes a corpus case, asks
the configured LLM backend to produce N semantic-preserving rephrasings of
the prompt, runs the skill against each variant, and checks whether the
judge's assertion verdicts are stable across variants.

Output is a stability score per case: `passing_variants / total_variants`.
A stable case (all variants produce the same verdicts) is robust to natural
prompt drift. An unstable case is brittle.

The fuzzer reuses the existing AgentRuntime + Judge plus an LLMBackend for
variant generation. It is opt-in via a new suite type registered behind the
suite name `fuzz`. Skills declare cases-to-fuzz in `evals/fuzz.json`:

    {
      "skill_name": "...",
      "evals": [
        { "id": ..., "prompt": "...", "expected_output": "...",
          "assertions": [...], "n_variants": 5 }
      ]
    }
"""

from __future__ import annotations

import time

from skillctl.agentskills import SkillFrontmatter
from skillctl.llm import LLMBackendError, build_backend
from skillctl.llm.base import LLMBackend
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

# Default number of rephrasings per case when the case does not declare one.
DEFAULT_N_VARIANTS = 4

_REPHRASE_SYSTEM = (
    "You generate semantic-preserving rephrasings of an input prompt for "
    "robustness testing. Return only the rephrased prompts, one per line, "
    "no numbering, no commentary. Preserve every concrete fact, parameter, "
    "and intent. Vary phrasing, word choice, and surface form."
)

_REPHRASE_PROMPT_TEMPLATE = """\
Original prompt:
{prompt}

Generate exactly {n} semantic-preserving rephrasings of the original prompt. \
One rephrasing per line, no numbering.\
"""


class SemanticFuzzer(Evaluator):
    """Suite name: `fuzz`. Runs each case against N rephrasings."""

    name = "fuzz"

    def __init__(
        self,
        *,
        skill: SkillFrontmatter,
        runtime: AgentRuntime,
        judge: Judge,
        backend: LLMBackend | None = None,
        n_variants: int = DEFAULT_N_VARIANTS,
    ) -> None:
        self._skill = skill
        self._runtime = runtime
        self._judge = judge
        self._backend = backend or build_backend()
        self._n_variants = n_variants

    def evaluate(self, suite: EvalSuite) -> SuiteResult:
        case_results = [self._evaluate_case(c) for c in suite.cases]
        return SuiteResult(
            suite_name=suite.name,
            skill_name=suite.skill_name,
            cases=case_results,
        )

    def _evaluate_case(self, case: EvalCase) -> CaseResult:
        started = time.monotonic()
        n = self._n_variants
        # Each case can override n_variants — read from the EvalCase if we
        # later extend the schema; for now use the evaluator default.

        variants = self._generate_variants(case.prompt, n=n)
        if not variants:
            # Backend failed; emit a runtime error rather than skipping silently.
            return CaseResult(
                case_id=case.id,
                prompt=case.prompt,
                expected_output=case.expected_output,
                actual_output="",
                assertions=[],
                duration_ms=int((time.monotonic() - started) * 1000),
                runtime_error="variant generation failed",
            )

        # Always include the original prompt as variant 0 — stability is
        # measured against the baseline.
        all_prompts = [case.prompt] + variants
        per_variant_results = self._evaluate_variants(case, all_prompts)

        # Stability = fraction of variants whose assertion verdicts exactly
        # match the baseline (variant 0).
        baseline = per_variant_results[0]
        baseline_pattern = [a.passed for a in baseline.assertions]
        stable_variants = sum(
            1
            for r in per_variant_results
            if [a.passed for a in r.assertions] == baseline_pattern
        )
        stability = stable_variants / len(per_variant_results)

        # The case-level assertion results are the baseline's — the actual
        # behavioural verdict. The metadata about stability is recorded as
        # synthetic assertions so the report surfaces it.
        synthetic = AssertionResult(
            assertion=f"output is stable across {n} rephrasings",
            passed=stability >= 0.75,
            reason=(
                f"{stable_variants}/{len(per_variant_results)} variants "
                f"matched the baseline assertion pattern "
                f"(stability={stability:.2f})"
            ),
        )

        all_assertions = list(baseline.assertions) + [synthetic]

        # Pick the actual_output from the variant with the most divergent
        # verdicts (most useful to the developer for debugging).
        divergent = max(
            per_variant_results,
            key=lambda r: sum(
                1
                for i, a in enumerate(r.assertions)
                if i < len(baseline_pattern) and a.passed != baseline_pattern[i]
            ),
        )

        return CaseResult(
            case_id=case.id,
            prompt=case.prompt,
            expected_output=case.expected_output,
            actual_output=divergent.actual_output,
            assertions=all_assertions,
            duration_ms=int((time.monotonic() - started) * 1000),
            runtime_error=None,
        )

    def _generate_variants(self, prompt: str, *, n: int) -> list[str]:
        try:
            resp = self._backend.complete(
                prompt=_REPHRASE_PROMPT_TEMPLATE.format(prompt=prompt, n=n),
                system=_REPHRASE_SYSTEM,
                max_tokens=512,
                temperature=0.7,  # higher temp for variant diversity
            )
        except LLMBackendError:
            return []

        # Split on newlines; drop empty and over-long lines.
        lines = [ln.strip() for ln in resp.text.splitlines() if ln.strip()]
        # Drop numbering prefixes the model sometimes ignores instructions about.
        cleaned = [_strip_numbering(ln) for ln in lines]
        # Cap to n variants.
        return cleaned[:n]

    def _evaluate_variants(
        self, case: EvalCase, prompts: list[str]
    ) -> list[CaseResult]:
        results: list[CaseResult] = []
        for i, prompt in enumerate(prompts):
            try:
                response = self._runtime.activate(self._skill, prompt)
                actual = response.reply
                error: str | None = None
            except Exception as exc:
                actual = ""
                error = f"{type(exc).__name__}: {exc}"

            assertion_results: list[AssertionResult] = []
            if error is None:
                for assertion in case.assertions:
                    verdict = self._judge.score(
                        assertion=assertion,
                        actual_output=actual,
                        expected_output=case.expected_output,
                    )
                    assertion_results.append(
                        AssertionResult(
                            assertion=assertion,
                            passed=verdict.passed,
                            reason=verdict.reason,
                        )
                    )

            results.append(
                CaseResult(
                    case_id=f"{case.id}#v{i}",
                    prompt=prompt,
                    expected_output=case.expected_output,
                    actual_output=actual,
                    assertions=assertion_results,
                    duration_ms=0,
                    runtime_error=error,
                )
            )
        return results


def _strip_numbering(line: str) -> str:
    """Strip leading '1. ', '1) ', '- ', '* ' from a rephrasing line."""
    for prefix_pattern in ((". ", ") "), ("- ", "* ")):
        for sep in prefix_pattern:
            if len(line) > 3 and line[0].isdigit() and line[1:3] == sep[-2:]:
                return line[3:].strip()
    for marker in ("- ", "* "):
        if line.startswith(marker):
            return line[len(marker):].strip()
    return line


__all__ = ["DEFAULT_N_VARIANTS", "SemanticFuzzer"]
