"""EvalRunner — orchestrate suites, runtimes, judges, and the cache.

Adds model pinning (runtime + judge model recorded in the report) and a
content-addressed cache so repeat runs with the same inputs return the same
report from disk instead of re-executing.

The runner accepts an `EvalConfig` (see `reproducibility.py`) that resolves
runtime + model + judge + judge backend + judge model + threshold. CLI flags
override config; config falls back to permissive defaults.
"""

from __future__ import annotations

from pathlib import Path

from skillctl.agentskills import parse_skill_md
from skillctl.run import build_runtime
from skillctl.strictness import Strictness

from .base import EvalMode, EvalReport, EvalSuite, SuiteResult
from .factory import build_evaluator, build_judge
from .loader import load_suites
from .reproducibility import (
    EvalConfig,
    cache_get,
    cache_put,
    compute_cache_key,
    compute_corpus_hash,
    compute_skill_hash,
)


class EvalRunner:
    """Run the configured eval suites with model pinning + cache."""

    def __init__(
        self,
        skill_dir: Path,
        strictness: Strictness,
        *,
        mode: EvalMode = EvalMode.FAST,
        config: EvalConfig | None = None,
        suite_filter: str | None = None,
        case_filter: str | None = None,
        use_cache: bool = False,
        refresh_cache: bool = False,
    ) -> None:
        self._skill_dir = skill_dir
        self._strictness = strictness
        self._mode = mode
        self._config = config or EvalConfig()
        self._suite_filter = suite_filter
        self._case_filter = case_filter
        self._use_cache = use_cache
        self._refresh_cache = refresh_cache

    def run(self) -> EvalReport:
        # Compute reproducibility hashes up front so a cache hit can short-circuit.
        skill_hash = compute_skill_hash(self._skill_dir)
        corpus_hash = compute_corpus_hash(self._skill_dir)
        cache_key = compute_cache_key(
            skill_hash=skill_hash,
            corpus_hash=corpus_hash,
            config=self._config,
            mode=self._mode,
            suite_filter=self._suite_filter,
            case_filter=self._case_filter,
        )

        if self._use_cache and not self._refresh_cache:
            cached = cache_get(cache_key)
            if cached is not None:
                return _report_from_cache(
                    cached,
                    skill_dir=self._skill_dir,
                    strictness=self._strictness,
                    config=self._config,
                    skill_hash=skill_hash,
                    corpus_hash=corpus_hash,
                    cache_key=cache_key,
                )

        # No cache hit — actually run.
        skill = parse_skill_md(self._skill_dir / "SKILL.md")
        runtime = build_runtime(
            self._config.runtime,
            model=self._config.runtime_model or None,
            max_tokens=self._config.runtime_max_tokens,
            temperature=self._config.runtime_temperature,
        )
        judge = self._build_judge()

        suites = load_suites(self._skill_dir / "evals")
        if self._suite_filter:
            suites = [s for s in suites if s.name == self._suite_filter]

        suite_results: list[SuiteResult] = []
        for suite in suites:
            cases = suite.cases
            if self._mode == EvalMode.SMOKE:
                cases = cases[:1]
            if self._case_filter:
                cases = [c for c in cases if c.id == self._case_filter]
            if not cases:
                continue

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

        report = EvalReport(
            skill_dir=self._skill_dir,
            strictness=self._strictness,
            mode=self._mode,
            runtime_name=self._config.runtime,
            judge_name=self._config.judge,
            suites=suite_results,
            runtime_model=self._config.runtime_model,
            judge_backend=self._config.judge_backend,
            judge_model=self._config.judge_model,
            skill_hash=skill_hash,
            corpus_hash=corpus_hash,
            cache_key=cache_key,
            cached=False,
            threshold=self._config.threshold,
        )

        if self._use_cache:
            cache_put(cache_key, _report_to_dict(report))

        return report

    def _build_judge(self):
        """Build the judge, passing backend/model/tunables when accepted."""
        if self._config.judge == "llm":
            from .llm_judge import LLMJudge

            return LLMJudge(
                backend_name=self._config.judge_backend or None,
                model=self._config.judge_model or None,
                max_tokens=self._config.judge_max_tokens,
            )
        if self._config.judge == "heuristic":
            from .judge import HeuristicJudge

            return HeuristicJudge(threshold=self._config.judge_threshold)
        return build_judge(self._config.judge)


def _report_to_dict(report: EvalReport) -> dict:
    """Serialize for the cache. Mirrors reproducibility._report_to_dict."""
    from .reproducibility import _report_to_dict as serialize

    return serialize(report)


def _report_from_cache(
    cached: dict,
    *,
    skill_dir: Path,
    strictness: Strictness,
    config: EvalConfig,
    skill_hash: str,
    corpus_hash: str,
    cache_key: str,
) -> EvalReport:
    """Rebuild an EvalReport from a cache dict.

    The cached dict carries the full case/assertion structure; we reconstruct
    just enough that the report's properties (score, passed, total_cases)
    compute correctly. Mark `cached=True` so the CLI can surface it.
    """
    from .base import AssertionResult, CaseResult, SuiteResult

    suite_results: list[SuiteResult] = []
    for s in cached.get("suites", []):
        cases: list[CaseResult] = []
        for c in s.get("cases", []):
            cases.append(
                CaseResult(
                    case_id=c.get("id", ""),
                    prompt=c.get("prompt", ""),
                    expected_output=c.get("expected_output", ""),
                    actual_output=c.get("actual_output", ""),
                    assertions=[
                        AssertionResult(
                            assertion=a.get("assertion", ""),
                            passed=bool(a.get("passed", False)),
                            reason=a.get("reason", ""),
                        )
                        for a in c.get("assertions", [])
                    ],
                    duration_ms=int(c.get("duration_ms", 0)),
                    runtime_error=c.get("runtime_error"),
                )
            )
        suite_results.append(
            SuiteResult(
                suite_name=s.get("name", ""),
                skill_name=s.get("skill_name", ""),
                cases=cases,
            )
        )

    return EvalReport(
        skill_dir=skill_dir,
        strictness=strictness,
        mode=EvalMode(cached.get("mode", "fast")),
        runtime_name=cached.get("runtime", config.runtime),
        judge_name=cached.get("judge", config.judge),
        suites=suite_results,
        runtime_model=config.runtime_model,
        judge_backend=config.judge_backend,
        judge_model=config.judge_model,
        skill_hash=skill_hash,
        corpus_hash=corpus_hash,
        cache_key=cache_key,
        cached=True,
        threshold=config.threshold,
    )


__all__ = ["EvalRunner"]
