"""Tests for `skillctl.eval` — loader, judge, runner, and the `bbsctl eval` command.

These tests exercise the eval pipeline end-to-end using the mock runtime and
the heuristic judge — no API key, no network. They are intentionally narrow:
each test asserts one behavior so failures localize quickly.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from skillctl.commands.eval_cmd import run as eval_run
from skillctl.eval import EvalMode, EvalRunner, HeuristicJudge
from skillctl.eval.loader import EvalLoadError, load_suites
from skillctl.strictness import Strictness


# ── fixtures ────────────────────────────────────────────────────────────────


def _write_skill(skill_dir: Path, *, body: str = "Reply with: \"hello world\"") -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        dedent(
            f"""\
            ---
            name: {skill_dir.name}
            description: A test skill for the eval module. The agent uses this
              skill whenever the user asks for a hello reply with at least one
              relevant action verb so the trigger validator is satisfied.
            ---

            # Test skill

            {body}
            """
        ),
        encoding="utf-8",
    )


def _write_suite(evals_dir: Path, name: str, cases: list[dict]) -> Path:
    evals_dir.mkdir(parents=True, exist_ok=True)
    path = evals_dir / f"{name}.json"
    path.write_text(
        json.dumps({"skill_name": evals_dir.parent.name, "evals": cases}, indent=2),
        encoding="utf-8",
    )
    return path


# ── HeuristicJudge ──────────────────────────────────────────────────────────


def test_heuristic_judge_passes_full_overlap():
    judge = HeuristicJudge()
    verdict = judge.score(
        assertion="kubectl rollout restart command is executed",
        actual_output="The kubectl rollout restart command is now executed",
        expected_output="",
    )
    assert verdict.passed
    assert "ratio=1.00" in verdict.reason


def test_heuristic_judge_fails_no_overlap():
    judge = HeuristicJudge()
    verdict = judge.score(
        assertion="kubectl rollout restart command is executed",
        actual_output="hello world",
        expected_output="",
    )
    assert not verdict.passed


def test_heuristic_judge_rejects_invalid_threshold():
    with pytest.raises(ValueError):
        HeuristicJudge(threshold=1.5)


# ── Loader ──────────────────────────────────────────────────────────────────


def test_load_suites_returns_empty_when_evals_dir_missing(tmp_path):
    assert load_suites(tmp_path / "nope") == []


def test_load_suites_parses_well_formed_json(tmp_path):
    skill = tmp_path / "my-skill"
    skill.mkdir()
    _write_suite(
        skill / "evals",
        "behavior",
        [
            {
                "id": 1,
                "prompt": "p",
                "expected_output": "e",
                "files": [],
                "assertions": ["a1", "a2"],
            }
        ],
    )

    suites = load_suites(skill / "evals")
    assert len(suites) == 1
    assert suites[0].name == "behavior"
    assert suites[0].skill_name == "my-skill"
    assert len(suites[0].cases) == 1
    assert suites[0].cases[0].id == "1"  # int coerced to str
    assert suites[0].cases[0].assertions == ["a1", "a2"]


def test_load_suites_rejects_malformed_json(tmp_path):
    evals = tmp_path / "skill" / "evals"
    evals.mkdir(parents=True)
    (evals / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(EvalLoadError) as exc_info:
        load_suites(evals)
    assert "not valid JSON" in exc_info.value.framework_error.summary


def test_load_suites_rejects_missing_skill_name(tmp_path):
    evals = tmp_path / "skill" / "evals"
    evals.mkdir(parents=True)
    (evals / "behavior.json").write_text(
        json.dumps({"evals": []}), encoding="utf-8"
    )

    with pytest.raises(EvalLoadError) as exc_info:
        load_suites(evals)
    assert "skill_name" in exc_info.value.framework_error.summary


def test_load_suites_rejects_case_without_id(tmp_path):
    evals = tmp_path / "skill" / "evals"
    evals.mkdir(parents=True)
    (evals / "behavior.json").write_text(
        json.dumps({"skill_name": "s", "evals": [{"prompt": "p"}]}),
        encoding="utf-8",
    )

    with pytest.raises(EvalLoadError) as exc_info:
        load_suites(evals)
    assert "missing `id`" in exc_info.value.framework_error.summary


# ── Runner ──────────────────────────────────────────────────────────────────


def test_eval_runner_returns_passing_report_when_assertions_match(tmp_path):
    skill = tmp_path / "hello"
    _write_skill(skill, body='Reply with: "kubectl rollout restart is executed"')
    _write_suite(
        skill / "evals",
        "behavior",
        [
            {
                "id": 1,
                "prompt": "trigger",
                "expected_output": "",
                "assertions": ["kubectl rollout restart command is executed"],
            }
        ],
    )

    report = EvalRunner(skill, Strictness.LOCAL).run()
    assert report.passed
    assert report.total_cases == 1
    assert report.passed_cases == 1


def test_eval_runner_smoke_mode_runs_only_first_case(tmp_path):
    skill = tmp_path / "hello"
    _write_skill(skill)
    _write_suite(
        skill / "evals",
        "behavior",
        [
            {"id": "a", "prompt": "p", "assertions": []},
            {"id": "b", "prompt": "p", "assertions": []},
            {"id": "c", "prompt": "p", "assertions": []},
        ],
    )

    report = EvalRunner(skill, Strictness.LOCAL, mode=EvalMode.SMOKE).run()
    assert report.total_cases == 1
    assert report.suites[0].cases[0].case_id == "a"


def test_eval_runner_case_filter(tmp_path):
    skill = tmp_path / "hello"
    _write_skill(skill)
    _write_suite(
        skill / "evals",
        "behavior",
        [
            {"id": "keep", "prompt": "p", "assertions": []},
            {"id": "drop", "prompt": "p", "assertions": []},
        ],
    )

    report = EvalRunner(
        skill, Strictness.LOCAL, case_filter="keep"
    ).run()
    assert report.total_cases == 1
    assert report.suites[0].cases[0].case_id == "keep"


def test_eval_runner_suite_filter_dropping_all_returns_empty(tmp_path):
    skill = tmp_path / "hello"
    _write_skill(skill)
    _write_suite(skill / "evals", "behavior", [{"id": 1, "prompt": "p"}])

    report = EvalRunner(
        skill, Strictness.LOCAL, suite_filter="does-not-exist"
    ).run()
    assert report.suites == []
    # An empty report is treated as "nothing to do, vacuously passing".
    assert report.passed


def test_eval_runner_case_with_no_assertions_passes(tmp_path):
    skill = tmp_path / "hello"
    _write_skill(skill)
    _write_suite(skill / "evals", "behavior", [{"id": 1, "prompt": "p"}])

    report = EvalRunner(skill, Strictness.LOCAL).run()
    # Empty assertions list ⇒ score 1.0 ⇒ case passes.
    assert report.passed
    assert report.suites[0].cases[0].score == 1.0


# ── CLI command ─────────────────────────────────────────────────────────────


class _Args:
    def __init__(self, **kwargs):
        self.skill_dir = kwargs.get("skill_dir", ".")
        self.mode = kwargs.get("mode", "fast")
        self.suite = kwargs.get("suite")
        self.case = kwargs.get("case")
        self.runtime = kwargs.get("runtime")           # None means use config default
        self.runtime_model = kwargs.get("runtime_model")
        self.runtime_max_tokens = kwargs.get("runtime_max_tokens")
        self.runtime_temperature = kwargs.get("runtime_temperature")
        self.judge = kwargs.get("judge")
        self.judge_backend = kwargs.get("judge_backend")
        self.judge_model = kwargs.get("judge_model")
        self.judge_threshold = kwargs.get("judge_threshold")
        self.judge_max_tokens = kwargs.get("judge_max_tokens")
        self.threshold = kwargs.get("threshold")
        self.fuzz_n_variants = kwargs.get("fuzz_n_variants")
        self.cache = kwargs.get("cache", False)
        self.refresh_cache = kwargs.get("refresh_cache", False)
        self.snapshot = kwargs.get("snapshot")
        self.strictness = kwargs.get("strictness")
        self.output = kwargs.get("output", "silent")


def test_eval_cmd_returns_2_when_evals_dir_missing(tmp_path, capsys):
    skill = tmp_path / "hello"
    _write_skill(skill)

    exit_code = eval_run(_Args(skill_dir=str(skill)))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no evals/ directory found" in captured.err


def test_eval_cmd_returns_2_when_skill_md_missing(tmp_path, capsys):
    # An evals dir without a SKILL.md beside it.
    skill = tmp_path / "hello"
    (skill / "evals").mkdir(parents=True)

    exit_code = eval_run(_Args(skill_dir=str(skill)))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "SKILL.md not found" in captured.err


def test_eval_cmd_returns_0_when_all_cases_pass(tmp_path):
    skill = tmp_path / "hello"
    _write_skill(skill, body='Reply with: "kubectl restart command executed"')
    _write_suite(
        skill / "evals",
        "behavior",
        [
            {
                "id": 1,
                "prompt": "p",
                "expected_output": "",
                "assertions": ["kubectl restart command executed"],
            }
        ],
    )

    assert eval_run(_Args(skill_dir=str(skill))) == 0


def test_eval_cmd_returns_1_when_a_case_fails(tmp_path):
    skill = tmp_path / "hello"
    _write_skill(skill, body='Reply with: "nothing related"')
    _write_suite(
        skill / "evals",
        "behavior",
        [
            {
                "id": 1,
                "prompt": "p",
                "assertions": ["kubectl rollout restart is executed"],
            }
        ],
    )

    assert eval_run(_Args(skill_dir=str(skill))) == 1


def test_eval_cmd_json_output_is_machine_readable(tmp_path, capsys):
    skill = tmp_path / "hello"
    _write_skill(skill)
    _write_suite(skill / "evals", "behavior", [{"id": 1, "prompt": "p"}])

    eval_run(_Args(skill_dir=str(skill), output="json"))

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert "suites" in parsed
    assert parsed["runtime"] == "mock"
    assert parsed["judge"] == "heuristic"
