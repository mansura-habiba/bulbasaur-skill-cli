"""EvalRunner — orchestrate loading suites and running evaluators.

The runner:

1. Loads the skill's frontmatter (so the runtime can activate it).
2. Discovers every `*.json` suite under `evals/`.
3. For each suite, builds the right Evaluator via the factory and runs it.
4. Aggregates results into an EvalReport.

Strictness gating is documented but not enforced here — that lives in the
publish gate (org+ refuses to host a skill whose eval report is missing or
not passing). Today the runner reports honestly; the gate is wired
incrementally as `org` strictness work lands.
"""

from __future__ import annotations

from pathlib import Path

from skillctl.agentskills import parse_skill_md
from skillctl.run import build_runtime
from skillctl.strictness import Strictness

from .base import EvalMode, EvalReport, SuiteResult
from .factory import build_evaluator, build_judge
from .loader import load_suites


class EvalRunner:
    """Run the configured eval suites against a skill directory."""

    def __init__(
        self,
        skill_dir: Path,
        strictness: Strictness,
        *,
        mode: EvalMode = EvalMode.FAST,
        runtime_name: str = "mock",
        judge_name: str = "heuristic",
        suite_filter: str | None = None,
        case_filter: str | None = None,
    ) -> None:
        self._skill_dir = skill_dir
        self._strictness = strictness
        self._mode = mode
        self._runtime_name = runtime_name
        self._judge_name = judge_name
        self._suite_filter = suite_filter
        self._case_filter = case_filter

    def run(self) -> EvalReport:
        skill = parse_skill_md(self._skill_dir / "SKILL.md")
        runtime = build_runtime(self._runtime_name)
        judge = build_judge(self._judge_name)

        suites = load_suites(self._skill_dir / "evals")
        if self._suite_filter:
            suites = [s for s in suites if s.name == self._suite_filter]

        suite_results: list[SuiteResult] = []
        for suite in suites:
            # Apply mode filter — SMOKE keeps the first case only.
            cases = suite.cases
            if self._mode == EvalMode.SMOKE:
                cases = cases[:1]
            if self._case_filter:
                cases = [c for c in cases if c.id == self._case_filter]

            if not cases:
                continue

            from .base import EvalSuite  # local import to avoid cycle on edit

            filtered = EvalSuite(
                name=suite.name,
                skill_name=suite.skill_name,
                source_path=suite.source_path,
                cases=cases,
            )

            evaluator = build_evaluator(
                suite.name, skill=skill, runtime=runtime, judge=judge
            )
            suite_results.append(evaluator.evaluate(filtered))

        return EvalReport(
            skill_dir=self._skill_dir,
            strictness=self._strictness,
            mode=self._mode,
            runtime_name=self._runtime_name,
            judge_name=self._judge_name,
            suites=suite_results,
        )


__all__ = ["EvalRunner"]
