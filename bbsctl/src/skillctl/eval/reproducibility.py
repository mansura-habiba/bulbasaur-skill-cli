"""Reproducible eval — `eval.config.yaml`, corpus/skill hashing, cache.

Three inputs determine an eval report's identity:

  (skill_hash, corpus_hash, runtime+model+judge+backend+model+mode)

Same three inputs → same output. The cache layer at `~/.cache/bbsctl/eval/`
keys reports by SHA-256 of the canonical input tuple so repeat runs in CI
are cheap and reproducible across machines.

The config file lives at `<skill>/evals/eval.config.yaml`:

    schema_version: bulbasaur/v1
    runtime: mock
    runtime_model: ""
    judge: heuristic
    judge_backend: ""        # only meaningful when judge=llm
    judge_model: ""          # only meaningful when judge=llm
    threshold: 1.0

Defaults apply when the file is absent. CLI flags override the config.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError

from .base import EvalMode, EvalReport

_CONFIG_NAME = "eval.config.yaml"
_DEFAULT_THRESHOLD = 1.0


@dataclass
class EvalConfig:
    """Resolved eval configuration after merging the cascade.

    Resolution chain (highest priority wins):
      1. CLI flag                  (override at command time)
      2. Environment variable      (session override)
      3. evals/eval.config.yaml    (skill-level config)
      4. pyproject.toml [tool.bulbasaur.eval]  (project-level)
      5. ~/.config/bbsctl/config.yaml  (user-level)
      6. /etc/bbsctl/config.yaml or $BBSCTL_ORG_CONFIG (org-level)
      7. Built-in default          (this dataclass)

    Every field below is tunable through every layer of the cascade.
    """

    # ── runtime ───────────────────────────────────────────────────────
    runtime: str = "mock"
    runtime_model: str = ""
    runtime_max_tokens: int = 4096
    runtime_temperature: float = 0.0

    # ── judge ─────────────────────────────────────────────────────────
    judge: str = "heuristic"
    judge_backend: str = ""
    judge_model: str = ""
    judge_threshold: float = 0.5         # heuristic-judge overlap ratio
    judge_max_tokens: int = 256          # LLMJudge per-assertion call

    # ── eval-suite knobs ──────────────────────────────────────────────
    threshold: float = _DEFAULT_THRESHOLD  # pass threshold across the suite
    fuzz_n_variants: int = 4              # SemanticFuzzer rephrasings per case

    def to_dict(self) -> dict:
        return {
            "runtime": self.runtime,
            "runtime_model": self.runtime_model,
            "runtime_max_tokens": self.runtime_max_tokens,
            "runtime_temperature": self.runtime_temperature,
            "judge": self.judge,
            "judge_backend": self.judge_backend,
            "judge_model": self.judge_model,
            "judge_threshold": self.judge_threshold,
            "judge_max_tokens": self.judge_max_tokens,
            "threshold": self.threshold,
            "fuzz_n_variants": self.fuzz_n_variants,
        }


class EvalConfigError(Exception):
    """Raised when eval.config.yaml is malformed."""

    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


def load_eval_config(skill_dir: Path) -> EvalConfig:
    """Load the eval config from the full cascade.

    Resolution order (highest wins):
      1. evals/eval.config.yaml  (skill-level)
      2. ~/.config/bbsctl/config.yaml  (user-level)
      3. /etc/bbsctl/config.yaml  (org-level)
      4. Built-in defaults

    Env vars (BBSCTL_EVAL_*) override the file layers; see user_config.py.
    Raises EvalConfigError only on malformed *skill-level* YAML.
    """
    path = skill_dir / "evals" / _CONFIG_NAME
    if not path.exists():
        # No skill-level file — return the user/org/env cascade verbatim.
        return _default_config_from_user_layer()

    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path)
    except Exception as exc:
        raise EvalConfigError(
            FrameworkError(
                summary="eval.config.yaml: YAML parse error",
                detail=str(exc),
                fix="Fix the YAML syntax. See docs/evaluation.md for the schema.",
                docs="../docs/evaluation.md",
            )
        ) from exc

    if not isinstance(raw, dict):
        raise EvalConfigError(
            FrameworkError(
                summary="eval.config.yaml: top-level must be a mapping",
                fix="Start with `schema_version: bulbasaur/v1`.",
            )
        )

    defaults = _default_config_from_user_layer()
    return EvalConfig(
        runtime=str(raw.get("runtime") or defaults.runtime),
        runtime_model=str(raw.get("runtime_model") or defaults.runtime_model),
        runtime_max_tokens=_safe_int(
            raw.get("runtime_max_tokens"), default=defaults.runtime_max_tokens
        ),
        runtime_temperature=_safe_float(
            raw.get("runtime_temperature"), default=defaults.runtime_temperature
        ),
        judge=str(raw.get("judge") or defaults.judge),
        judge_backend=str(raw.get("judge_backend") or defaults.judge_backend),
        judge_model=str(raw.get("judge_model") or defaults.judge_model),
        judge_threshold=_safe_float(
            raw.get("judge_threshold"), default=defaults.judge_threshold
        ),
        judge_max_tokens=_safe_int(
            raw.get("judge_max_tokens"), default=defaults.judge_max_tokens
        ),
        threshold=_safe_float(raw.get("threshold"), default=defaults.threshold),
        fuzz_n_variants=_safe_int(
            raw.get("fuzz_n_variants"), default=defaults.fuzz_n_variants
        ),
    )


def _default_config_from_user_layer() -> EvalConfig:
    """Load user-level + org-level defaults from disk + env.

    Lazy import to avoid a cycle (user_config imports messaging).
    """
    from skillctl.user_config import load_layered_eval_defaults

    return load_layered_eval_defaults()


def merge_config(base: EvalConfig, **overrides: Any) -> EvalConfig:
    """Layer CLI overrides on top of a base config. None/empty overrides ignored."""
    data = base.to_dict()
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        data[key] = value
    return EvalConfig(**data)


# ── hashing ─────────────────────────────────────────────────────────────────


def compute_skill_hash(skill_dir: Path) -> str:
    """SHA-256 over the SKILL.md content.

    The SKILL.md body drives runtime behavior; changing it invalidates the
    eval cache. Other files (skill.yaml, permissions.yaml) are separate
    artifacts evaluated independently.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return ""
    return _sha256_bytes(skill_md.read_bytes())


def compute_corpus_hash(skill_dir: Path) -> str:
    """SHA-256 over the concatenation of all suite files in lex order.

    Includes every `*.json` directly under `evals/`. Does not traverse
    subdirectories (snapshots/ etc.) so a snapshot write does not invalidate
    the cache.
    """
    evals_dir = skill_dir / "evals"
    if not evals_dir.is_dir():
        return ""

    h = hashlib.sha256()
    for path in sorted(evals_dir.glob("*.json")):
        h.update(path.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(path.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


def compute_cache_key(
    *,
    skill_hash: str,
    corpus_hash: str,
    config: EvalConfig,
    mode: EvalMode,
    suite_filter: str | None,
    case_filter: str | None,
) -> str:
    """SHA-256 over the canonical input tuple.

    Stable across machines: no absolute paths, no timestamps, sorted JSON.
    """
    payload = {
        "skill_hash": skill_hash,
        "corpus_hash": corpus_hash,
        "runtime": config.runtime,
        "runtime_model": config.runtime_model,
        "judge": config.judge,
        "judge_backend": config.judge_backend,
        "judge_model": config.judge_model,
        "mode": mode.value,
        "suite_filter": suite_filter or "",
        "case_filter": case_filter or "",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── cache ───────────────────────────────────────────────────────────────────


def cache_dir() -> Path:
    """Resolve the cache directory: $XDG_CACHE_HOME/bbsctl/eval or ~/.cache/bbsctl/eval."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(base) / "bbsctl" / "eval"


def cache_get(key: str) -> dict | None:
    """Read a cached report dict by key. Returns None on cache miss."""
    path = cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_put(key: str, report_dict: dict) -> Path:
    """Write a report dict to the cache and return the path."""
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{key}.json"
    path.write_text(json.dumps(report_dict, indent=2, default=str), encoding="utf-8")
    return path


# ── snapshot baselines ──────────────────────────────────────────────────────


def snapshot_path(skill_dir: Path, *, suite_name: str, runtime_model: str) -> Path:
    """Where a regression baseline for one suite + model is stored."""
    safe_model = runtime_model.replace("/", "_").replace(":", "_") or "default"
    return skill_dir / "evals" / "snapshots" / f"{suite_name}.{safe_model}.json"


def write_snapshot(
    report: EvalReport, *, suite_name: str, runtime_model: str
) -> Path:
    """Write the report to `evals/snapshots/<suite>.<model>.json`.

    Used by `bbsctl eval snapshot` to capture a baseline the next eval run
    can regression-compare against.
    """
    snap = snapshot_path(report.skill_dir, suite_name=suite_name, runtime_model=runtime_model)
    snap.parent.mkdir(parents=True, exist_ok=True)
    payload = _report_to_dict(report)
    snap.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return snap


def _report_to_dict(report: EvalReport) -> dict:
    """Serialize an EvalReport for cache / snapshot storage."""
    return {
        "passed": report.passed,
        "mode": report.mode.value,
        "strictness": report.strictness.value,
        "runtime": report.runtime_name,
        "judge": report.judge_name,
        "skill_dir": str(report.skill_dir),
        "score": report.score,
        "passed_cases": report.passed_cases,
        "total_cases": report.total_cases,
        "suites": [
            {
                "name": s.suite_name,
                "skill_name": s.skill_name,
                "passed": s.passed,
                "score": s.score,
                "passed_count": s.passed_count,
                "total_count": s.total_count,
                "cases": [
                    {
                        "id": c.case_id,
                        "prompt": c.prompt,
                        "expected_output": c.expected_output,
                        "actual_output": c.actual_output,
                        "passed": c.passed,
                        "score": c.score,
                        "duration_ms": c.duration_ms,
                        "runtime_error": c.runtime_error,
                        "assertions": [
                            {
                                "assertion": a.assertion,
                                "passed": a.passed,
                                "reason": a.reason,
                            }
                            for a in c.assertions
                        ],
                    }
                    for c in s.cases
                ],
            }
            for s in report.suites
        ],
    }


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "EvalConfig",
    "EvalConfigError",
    "cache_dir",
    "cache_get",
    "cache_put",
    "compute_cache_key",
    "compute_corpus_hash",
    "compute_skill_hash",
    "load_eval_config",
    "merge_config",
    "snapshot_path",
    "write_snapshot",
]
