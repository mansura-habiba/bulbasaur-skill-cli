"""Evaluator strategy interface and result types.

The data model mirrors the JSON format established by existing evals (see
README §Evaluating skills). Each suite is a JSON file with shape:

    {
      "skill_name": "...",
      "evals": [
        {
          "id": <int|str>,
          "prompt": "...",
          "expected_output": "...",
          "files": [],
          "assertions": ["...", "...", ...]
        }
      ]
    }

The eval pipeline is two-stage:

1. The configured AgentRuntime activates the skill against each prompt and
   returns the actual output.
2. The configured Judge scores each assertion against the actual output,
   returning pass/fail + a reason.

Case score = fraction of assertions that pass.
Suite score = mean across cases.
Run passes iff every suite's score ≥ threshold (default 1.0; configurable).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from skillctl.strictness import Strictness


class EvalMode(StrEnum):
    """Eval execution mode.

    SMOKE   one case per suite; sanity check the plumbing in CI
    FAST    every case, against the configured runtime + judge
    FULL    fast + regression compare against snapshots/
    """

    SMOKE = "smoke"
    FAST = "fast"
    FULL = "full"


@dataclass(frozen=True)
class EvalCase:
    """A single eval case as loaded from a suite file.

    The id is preserved as a string for stable reporting even when the source
    file used integer ids.
    """

    id: str
    prompt: str
    expected_output: str
    assertions: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvalSuite:
    """A named collection of cases loaded from one JSON file.

    The suite name is taken from the file's basename (e.g. `behavior.json` →
    `behavior`). The Evaluator implementation is chosen by suite name through
    the factory — `behavior` runs the BehaviorEvaluator, `injection` runs the
    InjectionEvaluator, etc.
    """

    name: str
    skill_name: str
    source_path: Path
    cases: list[EvalCase] = field(default_factory=list)


@dataclass
class AssertionResult:
    """Result of scoring one assertion against one case's actual output."""

    assertion: str
    passed: bool
    reason: str = ""


@dataclass
class CaseResult:
    """Result of running one case end-to-end."""

    case_id: str
    prompt: str
    expected_output: str
    actual_output: str
    assertions: list[AssertionResult] = field(default_factory=list)
    duration_ms: int = 0
    runtime_error: str | None = None

    @property
    def score(self) -> float:
        """Fraction of assertions that passed. 1.0 if no assertions declared."""
        if not self.assertions:
            return 1.0
        passed = sum(1 for a in self.assertions if a.passed)
        return passed / len(self.assertions)

    @property
    def passed(self) -> bool:
        return self.runtime_error is None and self.score == 1.0


@dataclass
class SuiteResult:
    """Aggregated result for one suite."""

    suite_name: str
    skill_name: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.cases:
            return 1.0
        return sum(c.score for c in self.cases) / len(self.cases)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cases)


@dataclass
class EvalReport:
    """Top-level report from one EvalRunner.run().

    Reproducibility metadata (model versions, hashes, cache state) is
    populated by the runner so the report is self-describing — a future run
    with the same inputs returns the same report.
    """

    skill_dir: Path
    strictness: Strictness
    mode: EvalMode
    runtime_name: str
    judge_name: str
    suites: list[SuiteResult] = field(default_factory=list)

    # Reproducibility / pinning metadata. Populated by EvalRunner.
    runtime_model: str = ""
    judge_backend: str = ""
    judge_model: str = ""
    skill_hash: str = ""
    corpus_hash: str = ""
    cache_key: str = ""
    cached: bool = False
    threshold: float = 1.0

    @property
    def score(self) -> float:
        if not self.suites:
            return 1.0
        return sum(s.score for s in self.suites) / len(self.suites)

    @property
    def passed(self) -> bool:
        if not self.suites:
            return True
        # Threshold IS the gate. With the default threshold=1.0 this is
        # equivalent to "every case passes"; lower thresholds let runs
        # pass with partial assertion coverage.
        return self.score >= self.threshold

    @property
    def total_cases(self) -> int:
        return sum(s.total_count for s in self.suites)

    @property
    def passed_cases(self) -> int:
        return sum(s.passed_count for s in self.suites)


class Evaluator(ABC):
    """Strategy interface for an evaluator.

    Concrete implementations (BehaviorEvaluator, TriggerEvaluator,
    InjectionEvaluator, RegressionEvaluator) are registered through
    skillctl.eval.factory. The runner picks an Evaluator by suite name.
    """

    #: Short name used in reports and CLI flags. Must match the suite filename
    #: (without extension) the evaluator is responsible for.
    name: str = "anonymous-evaluator"

    def applies_to(self, strictness: Strictness) -> bool:
        """Return False to skip this evaluator at a given strictness level."""
        return True

    @abstractmethod
    def evaluate(self, suite: EvalSuite) -> SuiteResult:
        """Run every case in the suite and return aggregated results."""


__all__ = [
    "AssertionResult",
    "CaseResult",
    "EvalCase",
    "EvalMode",
    "EvalReport",
    "EvalSuite",
    "Evaluator",
    "SuiteResult",
]
