"""Opt-in behavioral assessment using skillctl's existing EvalRunner.

The caller provides cases, not filenames or executable configuration. An
operator-owned configuration controls which execution backends may run. This
module never silently treats a mock run as real-agent qualification.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillctl.eval.base import EvalMode
from skillctl.eval.reproducibility import EvalConfig
from skillctl.eval.runner import EvalRunner
from skillctl.strictness import Strictness

MAX_CASES = 12
MAX_PROMPT_CHARS = 4096
MAX_ASSERTIONS = 8
MAX_ASSERTION_CHARS = 512
_ALLOWED_FIELDS = {"enabled", "runtime", "judge", "cases", "threshold"}
_ALLOWED_RUNTIME = {"mock", "ollama"}
_ALLOWED_JUDGE = {"heuristic"}
_ALLOWED_CONFIG_FIELDS = {"allowed_runtimes", "max_cases", "enable_real_runtimes"}


class EvaluationConfigurationError(ValueError):
    """A caller-requested evaluation cannot be admitted."""


@dataclass(frozen=True)
class OperatorPolicy:
    allowed_runtimes: frozenset[str] = frozenset({"mock"})
    max_cases: int = MAX_CASES
    enable_real_runtimes: bool = False


def load_operator_policy(path: str | None = None) -> OperatorPolicy:
    """Read deployment-owned JSON; the caller cannot supply this file path."""
    filename = path or os.environ.get("BULBASAUR_EVAL_CONFIG")
    if not filename:
        return OperatorPolicy()
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) - _ALLOWED_CONFIG_FIELDS:
        raise EvaluationConfigurationError("Invalid operator evaluation configuration")
    runtimes = data.get("allowed_runtimes", ["mock"])
    if not isinstance(runtimes, list) or not runtimes or any(
        not isinstance(item, str) or item not in _ALLOWED_RUNTIME for item in runtimes
    ):
        raise EvaluationConfigurationError("Invalid configured runtime allowlist")
    maximum = data.get("max_cases", MAX_CASES)
    if type(maximum) is not int or not 1 <= maximum <= MAX_CASES:
        raise EvaluationConfigurationError("Invalid evaluation case limit")
    enabled = data.get("enable_real_runtimes", False)
    if type(enabled) is not bool:
        raise EvaluationConfigurationError("Invalid real-runtime enable flag")
    if not enabled and any(runtime != "mock" for runtime in runtimes):
        raise EvaluationConfigurationError("Real runtime requires operator opt-in")
    return OperatorPolicy(frozenset(runtimes), maximum, enabled)


def normalize_request(value: Any, *, policy: OperatorPolicy) -> dict[str, Any] | None:
    """Validate an inline request before constructing a runtime or writing a suite."""
    if value is None or value == {"enabled": False}:
        return None
    if not isinstance(value, dict) or set(value) - _ALLOWED_FIELDS:
        raise EvaluationConfigurationError("Unexpected evaluation request fields")
    if value.get("enabled") is not True:
        raise EvaluationConfigurationError("Evaluation requires enabled=true")
    runtime = value.get("runtime", "mock")
    judge = value.get("judge", "heuristic")
    if not isinstance(runtime, str) or runtime not in policy.allowed_runtimes or runtime not in _ALLOWED_RUNTIME:
        raise EvaluationConfigurationError("Runtime not permitted by operator configuration")
    if not isinstance(judge, str) or judge not in _ALLOWED_JUDGE:
        raise EvaluationConfigurationError("Only the heuristic judge is available via this API")
    if runtime != "mock" and not policy.enable_real_runtimes:
        raise EvaluationConfigurationError("Real runtimes are disabled")
    threshold = value.get("threshold", 1.0)
    if type(threshold) not in (float, int) or not 0 <= threshold <= 1:
        raise EvaluationConfigurationError("threshold must be between 0 and 1")
    cases = value.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= policy.max_cases:
        raise EvaluationConfigurationError("Provide 1 to the configured maximum of cases")
    ids: set[str] = set()
    normalized = []
    for case in cases:
        if not isinstance(case, dict) or set(case) - {"id", "prompt", "expected_output", "assertions"}:
            raise EvaluationConfigurationError("Invalid evaluation case fields")
        case_id = case.get("id")
        prompt = case.get("prompt")
        expected = case.get("expected_output", "")
        assertions = case.get("assertions")
        if not isinstance(case_id, str) or not 1 <= len(case_id) <= 64 or case_id in ids:
            raise EvaluationConfigurationError("Case IDs must be unique nonempty strings")
        ids.add(case_id)
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= MAX_PROMPT_CHARS:
            raise EvaluationConfigurationError("Invalid case prompt")
        if not isinstance(expected, str) or len(expected) > MAX_PROMPT_CHARS:
            raise EvaluationConfigurationError("Invalid expected output")
        if not isinstance(assertions, list) or not 1 <= len(assertions) <= MAX_ASSERTIONS:
            raise EvaluationConfigurationError("Each case requires bounded assertions")
        if any(not isinstance(a, str) or not 1 <= len(a) <= MAX_ASSERTION_CHARS for a in assertions):
            raise EvaluationConfigurationError("Invalid case assertion")
        normalized.append({"id": case_id, "prompt": prompt,
                           "expected_output": expected, "assertions": assertions})
    return {"runtime": runtime, "judge": judge, "threshold": float(threshold),
            "cases": normalized}


def run_behavioral_evaluation(
    skill_dir: Path, skill_name: str, request: dict[str, Any]
) -> dict[str, Any]:
    """Run exactly the validated inline suite without external cache reuse."""
    eval_dir = skill_dir / "evals"
    eval_dir.mkdir(exist_ok=True)
    corpus = {"skill_name": skill_name, "evals": request["cases"]}
    encoded = json.dumps(corpus, sort_keys=True, separators=(",", ":"))
    (eval_dir / "behavior.json").write_text(encoded, encoding="utf-8")
    config = EvalConfig(runtime=request["runtime"], judge=request["judge"],
                        threshold=request["threshold"])
    report = EvalRunner(skill_dir, Strictness.LOCAL, mode=EvalMode.FAST,
                        config=config, suite_filter="behavior", use_cache=False).run()
    total = report.total_cases
    status = "passed" if total and report.passed and report.passed_cases == total else "failed"
    # Deliberately do not return prompt or model output, which may contain secrets.
    return {
        "status": status,
        "runtime": request["runtime"],
        "judge": request["judge"],
        "mode": "deterministic_mock" if request["runtime"] == "mock" else "agent_runtime",
        "cases_run": total,
        "cases_passed": report.passed_cases,
        "score": report.score if total else 0.0,
        "corpus_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "case_results": [
            {"id": c.case_id, "passed": c.passed, "score": c.score,
             "error": bool(c.runtime_error)}
            for suite in report.suites for c in suite.cases
        ],
    }
