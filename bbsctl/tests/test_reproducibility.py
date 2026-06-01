"""Tests for the reproducible-eval layer: config, hashing, cache, snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from skillctl.eval.base import EvalMode
from skillctl.eval.reproducibility import (
    EvalConfig,
    EvalConfigError,
    cache_dir,
    cache_get,
    cache_put,
    compute_cache_key,
    compute_corpus_hash,
    compute_skill_hash,
    load_eval_config,
    merge_config,
    snapshot_path,
)


# ── helpers ────────────────────────────────────────────────────────────────


def _write_skill(skill_dir: Path, body: str = "Reply with: \"hello\"") -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        dedent(
            f"""\
            ---
            name: {skill_dir.name}
            description: a skill for testing
            ---

            {body}
            """
        ),
        encoding="utf-8",
    )


def _write_suite(skill_dir: Path, suite_name: str, cases: list[dict]) -> Path:
    evals = skill_dir / "evals"
    evals.mkdir(parents=True, exist_ok=True)
    path = evals / f"{suite_name}.json"
    path.write_text(
        json.dumps({"skill_name": skill_dir.name, "evals": cases}, indent=2),
        encoding="utf-8",
    )
    return path


def _write_eval_config(skill_dir: Path, content: str) -> Path:
    evals = skill_dir / "evals"
    evals.mkdir(parents=True, exist_ok=True)
    path = evals / "eval.config.yaml"
    path.write_text(dedent(content), encoding="utf-8")
    return path


# ── EvalConfig load + merge ────────────────────────────────────────────────


def test_load_eval_config_returns_defaults_when_absent(tmp_path):
    config = load_eval_config(tmp_path)
    assert config.runtime == "mock"
    assert config.judge == "heuristic"
    assert config.threshold == 1.0


def test_load_eval_config_reads_fields(tmp_path):
    _write_eval_config(tmp_path, """\
        schema_version: bulbasaur/v1
        runtime: mock
        runtime_model: claude-sonnet-4-6
        judge: llm
        judge_backend: anthropic
        judge_model: claude-haiku-4-5-20251001
        threshold: 0.9
    """)
    c = load_eval_config(tmp_path)
    assert c.runtime_model == "claude-sonnet-4-6"
    assert c.judge == "llm"
    assert c.judge_backend == "anthropic"
    assert c.judge_model == "claude-haiku-4-5-20251001"
    assert c.threshold == 0.9


def test_load_eval_config_rejects_malformed_yaml(tmp_path):
    _write_eval_config(tmp_path, "runtime: [unclosed\n")
    with pytest.raises(EvalConfigError):
        load_eval_config(tmp_path)


def test_load_eval_config_rejects_non_mapping(tmp_path):
    _write_eval_config(tmp_path, "- list\n- not mapping\n")
    with pytest.raises(EvalConfigError):
        load_eval_config(tmp_path)


def test_merge_config_overrides_non_empty_fields():
    base = EvalConfig(runtime="mock", judge="heuristic", threshold=1.0)
    merged = merge_config(base, runtime="claude-agent-sdk", judge="llm")
    assert merged.runtime == "claude-agent-sdk"
    assert merged.judge == "llm"
    assert merged.threshold == 1.0  # untouched


def test_merge_config_ignores_none_and_empty_strings():
    base = EvalConfig(runtime="mock", runtime_model="custom")
    merged = merge_config(base, runtime=None, runtime_model="")
    assert merged.runtime == "mock"
    assert merged.runtime_model == "custom"


# ── hashing ─────────────────────────────────────────────────────────────────


def test_skill_hash_is_deterministic_and_changes_with_content(tmp_path):
    skill = tmp_path / "s"
    _write_skill(skill, body="Reply with: \"a\"")
    h1 = compute_skill_hash(skill)
    h2 = compute_skill_hash(skill)
    assert h1 == h2
    _write_skill(skill, body="Reply with: \"b\"")
    h3 = compute_skill_hash(skill)
    assert h1 != h3


def test_skill_hash_empty_when_skill_md_absent(tmp_path):
    assert compute_skill_hash(tmp_path) == ""


def test_corpus_hash_covers_every_suite_file(tmp_path):
    skill = tmp_path / "s"
    _write_skill(skill)
    _write_suite(skill, "behavior", [{"id": 1, "prompt": "p"}])
    h1 = compute_corpus_hash(skill)
    _write_suite(skill, "injection", [{"id": "inj-1", "prompt": "p"}])
    h2 = compute_corpus_hash(skill)
    assert h1 != h2  # new suite invalidates hash


def test_corpus_hash_ignores_subdirectories(tmp_path):
    skill = tmp_path / "s"
    _write_skill(skill)
    _write_suite(skill, "behavior", [{"id": 1, "prompt": "p"}])
    h1 = compute_corpus_hash(skill)
    # Write a snapshot — must not affect the corpus hash.
    snap_dir = skill / "evals" / "snapshots"
    snap_dir.mkdir()
    (snap_dir / "behavior.json").write_text("{}", encoding="utf-8")
    h2 = compute_corpus_hash(skill)
    assert h1 == h2


def test_corpus_hash_empty_when_evals_dir_missing(tmp_path):
    assert compute_corpus_hash(tmp_path) == ""


# ── cache key ──────────────────────────────────────────────────────────────


def test_cache_key_stable_for_same_inputs():
    config = EvalConfig(runtime="mock", runtime_model="m", judge="llm")
    k1 = compute_cache_key(
        skill_hash="abc",
        corpus_hash="def",
        config=config,
        mode=EvalMode.FAST,
        suite_filter=None,
        case_filter=None,
    )
    k2 = compute_cache_key(
        skill_hash="abc",
        corpus_hash="def",
        config=config,
        mode=EvalMode.FAST,
        suite_filter=None,
        case_filter=None,
    )
    assert k1 == k2


def test_cache_key_changes_when_model_changes():
    base = dict(
        skill_hash="abc",
        corpus_hash="def",
        mode=EvalMode.FAST,
        suite_filter=None,
        case_filter=None,
    )
    k_m1 = compute_cache_key(config=EvalConfig(runtime_model="m1"), **base)
    k_m2 = compute_cache_key(config=EvalConfig(runtime_model="m2"), **base)
    assert k_m1 != k_m2


def test_cache_key_changes_with_mode_and_filters():
    config = EvalConfig()
    base = dict(skill_hash="abc", corpus_hash="def", config=config)
    k_fast = compute_cache_key(**base, mode=EvalMode.FAST, suite_filter=None, case_filter=None)
    k_smoke = compute_cache_key(**base, mode=EvalMode.SMOKE, suite_filter=None, case_filter=None)
    k_suite = compute_cache_key(**base, mode=EvalMode.FAST, suite_filter="behavior", case_filter=None)
    assert len({k_fast, k_smoke, k_suite}) == 3


# ── cache I/O ──────────────────────────────────────────────────────────────


def test_cache_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_dir() == tmp_path / "bbsctl" / "eval"


def test_cache_put_then_get_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    payload = {"passed": True, "score": 1.0}
    cache_put("test-key", payload)
    assert cache_get("test-key") == payload


def test_cache_get_miss_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_get("nonexistent-key") is None


def test_cache_get_tolerates_corrupt_file(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    d = cache_dir()
    d.mkdir(parents=True)
    (d / "corrupt.json").write_text("not json", encoding="utf-8")
    assert cache_get("corrupt") is None


# ── snapshot path ──────────────────────────────────────────────────────────


def test_snapshot_path_sanitizes_model_name(tmp_path):
    p = snapshot_path(tmp_path, suite_name="behavior", runtime_model="vendor/model:v1")
    assert p.parent == tmp_path / "evals" / "snapshots"
    # `/` and `:` replaced.
    assert "vendor_model_v1" in p.name


def test_snapshot_path_default_when_model_empty(tmp_path):
    p = snapshot_path(tmp_path, suite_name="behavior", runtime_model="")
    assert "default" in p.name


# ── EvalRunner with cache + pinning integration ────────────────────────────


def test_runner_cache_hit_returns_cached_report(monkeypatch, tmp_path):
    """End-to-end: run with --cache, then run again — second run reads from cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    from skillctl.eval import EvalRunner
    from skillctl.strictness import Strictness

    skill = tmp_path / "skill"
    _write_skill(skill, body='Reply with: "the answer"')
    _write_suite(
        skill,
        "behavior",
        [
            {
                "id": 1,
                "prompt": "trigger",
                "expected_output": "",
                "assertions": ["answer"],
            }
        ],
    )

    config = EvalConfig(runtime="mock", judge="heuristic", threshold=0.0)
    runner = EvalRunner(
        skill,
        Strictness.LOCAL,
        config=config,
        use_cache=True,
    )
    report1 = runner.run()
    assert report1.cached is False
    assert report1.cache_key  # was computed

    # Second run with the same inputs hits the cache.
    runner2 = EvalRunner(
        skill,
        Strictness.LOCAL,
        config=config,
        use_cache=True,
    )
    report2 = runner2.run()
    assert report2.cached is True
    assert report2.cache_key == report1.cache_key


def test_runner_refresh_cache_skips_read_but_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    from skillctl.eval import EvalRunner
    from skillctl.strictness import Strictness

    skill = tmp_path / "skill"
    _write_skill(skill)
    _write_suite(skill, "behavior", [{"id": 1, "prompt": "p", "assertions": []}])

    config = EvalConfig()
    EvalRunner(skill, Strictness.LOCAL, config=config, use_cache=True).run()

    # Refresh — must NOT report cached=True.
    report = EvalRunner(
        skill,
        Strictness.LOCAL,
        config=config,
        use_cache=True,
        refresh_cache=True,
    ).run()
    assert report.cached is False


def test_runner_records_pinning_metadata_in_report(tmp_path):
    from skillctl.eval import EvalRunner
    from skillctl.strictness import Strictness

    skill = tmp_path / "skill"
    _write_skill(skill)
    _write_suite(skill, "behavior", [{"id": 1, "prompt": "p", "assertions": []}])

    config = EvalConfig(
        runtime="mock",
        runtime_model="custom-mock-model",
        judge="heuristic",
        threshold=0.5,
    )
    report = EvalRunner(skill, Strictness.LOCAL, config=config).run()
    assert report.runtime_model == "custom-mock-model"
    assert report.threshold == 0.5
    assert report.skill_hash != ""
    assert report.corpus_hash != ""
    assert report.cache_key != ""


def test_runner_threshold_gates_passing(tmp_path):
    """A run that scores 0.5 passes when threshold=0.5 and fails when threshold=1.0."""
    from skillctl.eval import EvalRunner
    from skillctl.strictness import Strictness

    skill = tmp_path / "skill"
    _write_skill(skill, body='Reply with: "matches keyword one"')
    _write_suite(
        skill,
        "behavior",
        [
            {
                "id": 1,
                "prompt": "p",
                "expected_output": "",
                "assertions": [
                    "matches keyword one",
                    "different unrelated assertion",
                ],
            }
        ],
    )

    # Heuristic judge passes the first assertion, fails the second.
    permissive = EvalConfig(threshold=0.5)
    strict = EvalConfig(threshold=1.0)

    r_permissive = EvalRunner(skill, Strictness.LOCAL, config=permissive).run()
    r_strict = EvalRunner(skill, Strictness.LOCAL, config=strict).run()

    assert r_permissive.score == r_strict.score  # same actual score
    assert r_permissive.passed is True
    assert r_strict.passed is False
