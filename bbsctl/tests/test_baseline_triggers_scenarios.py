"""Tests for the three eval extensions:

  1. BaselineEvaluator — A/B with-vs-without skill
  2. TriggerEvaluator — activation precision/recall on positive/negative cases
  3. Scenario loader — YAML spec + tasks + fixtures, with {{fixture:…}} and
     {{vars.…}} substitution

Plus integration through bbsctl eval --baseline + suite=triggers and
scenarios alongside the JSON suites.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from skillctl.agentskills import SkillFrontmatter
from skillctl.eval import EvalRunner
from skillctl.eval.base import (
    AssertionResult,
    EvalCase,
    EvalSuite,
    SuiteResult,
)
from skillctl.eval.baseline import (
    BaselineEvaluator,
    BaselineSuiteSummary,
    get_baseline_summary,
)
from skillctl.eval.factory import build_evaluator, list_evaluators
from skillctl.eval.judge import HeuristicJudge
from skillctl.eval.reproducibility import EvalConfig
from skillctl.eval.scenario import (
    ScenarioLoadError,
    ScenarioSpec,
    load_scenarios,
)
from skillctl.eval.triggers import (
    DEFAULT_ACTIVATION_THRESHOLD,
    TriggerEvaluator,
    get_trigger_summary,
)
from skillctl.run.runtime import AgentRuntime, RuntimeResponse
from skillctl.strictness import Strictness


# ── helpers ──────────────────────────────────────────────────────────────


def _skill(body: str = 'Reply with: "the skill answer matches"') -> SkillFrontmatter:
    return SkillFrontmatter(
        raw_frontmatter={
            "name": "test-skill",
            "description": "When the user asks anything, reply with the standard skill answer.",
        },
        body=body,
        body_line_offset=4,
    )


class _SkillAwareRuntime(AgentRuntime):
    """Returns different replies depending on whether the skill body is empty.

    Used to demonstrate that A/B baseline mode runs both passes and that the
    deltas are computed correctly. When `skill.body` is empty, returns the
    `no_skill_reply`; otherwise returns `with_skill_reply`.
    """

    name = "skill-aware"

    def __init__(self, *, with_skill_reply: str, no_skill_reply: str) -> None:
        self._with = with_skill_reply
        self._no = no_skill_reply

    def activate(self, skill: SkillFrontmatter, prompt: str) -> RuntimeResponse:
        reply = self._with if skill.body else self._no
        return RuntimeResponse(
            activated_skill=skill.name or "x",
            reply=reply,
            trace=[],
            metadata={},
        )


class _ConstantRuntime(AgentRuntime):
    """Returns the same reply regardless of skill — baseline shouldn't differ."""

    name = "constant"

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def activate(self, skill, prompt):
        return RuntimeResponse(
            activated_skill=skill.name or "x",
            reply=self._reply,
            trace=[],
            metadata={},
        )


def _suite(case_id: str, prompt: str, assertions: list[str]) -> EvalSuite:
    return EvalSuite(
        name="behavior",
        skill_name="t",
        source_path=Path("/dev/null"),
        cases=[
            EvalCase(
                id=case_id,
                prompt=prompt,
                expected_output="",
                assertions=assertions,
            )
        ],
    )


# ── BaselineEvaluator ────────────────────────────────────────────────────


def test_baseline_reports_positive_delta_when_skill_helps():
    """With-skill reply matches the assertion; without-skill reply doesn't."""
    rt = _SkillAwareRuntime(
        with_skill_reply="the skill answer matches the assertion keywords",
        no_skill_reply="generic boilerplate not related",
    )
    judge = HeuristicJudge(threshold=0.3)
    skill = _skill()
    suite = _suite(
        "c-001",
        "trigger",
        ["the skill answer matches"],
    )
    result = BaselineEvaluator(skill=skill, runtime=rt, judge=judge).evaluate(suite)

    summary = get_baseline_summary(result)
    assert summary is not None
    assert summary.pass_rate_with_skill == pytest.approx(1.0)
    assert summary.pass_rate_without_skill == pytest.approx(0.0)
    assert summary.pass_rate_delta == pytest.approx(1.0)
    assert summary.cases_helped == 1
    assert summary.cases_hurt == 0


def test_baseline_reports_no_delta_when_skill_irrelevant():
    """Constant runtime — both passes return the same reply, delta = 0."""
    rt = _ConstantRuntime("the skill answer matches always")
    judge = HeuristicJudge(threshold=0.3)
    suite = _suite("c-001", "trigger", ["the skill answer matches"])
    result = BaselineEvaluator(
        skill=_skill(), runtime=rt, judge=judge
    ).evaluate(suite)
    summary = get_baseline_summary(result)
    assert summary.score_delta == pytest.approx(0.0)
    assert summary.cases_helped == 0
    assert summary.cases_unchanged == 1


def test_baseline_synthetic_assertion_appended_to_each_case():
    rt = _SkillAwareRuntime(
        with_skill_reply="the skill answer matches",
        no_skill_reply="nothing",
    )
    suite = _suite("c-001", "trigger", ["the skill answer matches"])
    result = BaselineEvaluator(
        skill=_skill(), runtime=rt, judge=HeuristicJudge(threshold=0.3)
    ).evaluate(suite)
    case = result.cases[0]
    # Original assertion + synthetic baseline assertion.
    assert len(case.assertions) == 2
    assert "baseline" in case.assertions[-1].assertion


def test_baseline_suite_name_is_decorated():
    rt = _ConstantRuntime("anything")
    suite = _suite("c", "p", [])
    result = BaselineEvaluator(
        skill=_skill(), runtime=rt, judge=HeuristicJudge()
    ).evaluate(suite)
    assert "+baseline" in result.suite_name


# ── TriggerEvaluator ─────────────────────────────────────────────────────


def _trigger_suite(case_id: str, prompt: str, assertions: list[str]) -> EvalSuite:
    return EvalSuite(
        name="triggers",
        skill_name="t",
        source_path=Path("/dev/null"),
        cases=[
            EvalCase(
                id=case_id,
                prompt=prompt,
                expected_output="",
                assertions=assertions,
            )
        ],
    )


def test_trigger_positive_case_passes_when_assertions_match():
    rt = _ConstantRuntime("kubectl rollout restart is mentioned, healthy")
    judge = HeuristicJudge(threshold=0.3)
    ev = TriggerEvaluator(skill=_skill(), runtime=rt, judge=judge)
    suite = _trigger_suite("pos-001", "restart deployment", ["kubectl rollout restart"])
    result = ev.evaluate(suite)
    case = result.cases[0]
    # Last assertion is the synthetic classification — should pass for positive.
    assert case.assertions[-1].passed
    assert "positive case" in case.assertions[-1].assertion


def test_trigger_positive_case_fails_when_skill_does_not_apply():
    rt = _ConstantRuntime("generic boilerplate not related")
    judge = HeuristicJudge(threshold=0.3)
    suite = _trigger_suite("pos-002", "restart", ["kubectl rollout restart command"])
    result = TriggerEvaluator(
        skill=_skill(), runtime=rt, judge=judge
    ).evaluate(suite)
    case = result.cases[0]
    # Classification assertion should report the failure.
    assert not case.assertions[-1].passed


def test_trigger_negative_case_passes_when_skill_does_not_activate():
    """Negative case — assertions should NOT match → activation = False → PASS."""
    rt = _ConstantRuntime("the weather today is sunny")
    judge = HeuristicJudge(threshold=0.3)
    suite = _trigger_suite("neg-001", "weather?", ["kubectl rollout restart"])
    result = TriggerEvaluator(
        skill=_skill(), runtime=rt, judge=judge
    ).evaluate(suite)
    case = result.cases[0]
    assert case.assertions[-1].passed
    assert "negative case" in case.assertions[-1].assertion


def test_trigger_negative_case_fails_on_false_positive():
    """Skill activates on a negative case — false positive."""
    rt = _ConstantRuntime("kubectl rollout restart was executed")
    judge = HeuristicJudge(threshold=0.3)
    suite = _trigger_suite("neg-002", "weather?", ["kubectl rollout restart"])
    result = TriggerEvaluator(
        skill=_skill(), runtime=rt, judge=judge
    ).evaluate(suite)
    assert not result.cases[0].assertions[-1].passed


def test_trigger_summary_aggregates_precision_recall_f1():
    rt_with_skill = _ConstantRuntime("kubectl rollout restart was executed")
    rt_without_skill = _ConstantRuntime("the weather today is sunny")
    judge = HeuristicJudge(threshold=0.3)

    # Build a small mixed suite via two single-case evaluations.
    suite_pos = _trigger_suite("pos-001", "restart", ["kubectl rollout restart"])
    suite_neg = _trigger_suite("neg-001", "weather?", ["kubectl rollout restart"])
    suite_pos.cases[0]
    pos_result = TriggerEvaluator(
        skill=_skill(), runtime=rt_with_skill, judge=judge
    ).evaluate(suite_pos)
    neg_result = TriggerEvaluator(
        skill=_skill(), runtime=rt_without_skill, judge=judge
    ).evaluate(suite_neg)
    # Pos case: skill activated (TP). Neg case: skill didn't activate (TN).
    assert get_trigger_summary(pos_result)["true_positive"] == 1
    assert get_trigger_summary(neg_result)["true_negative"] == 1


def test_factory_builds_triggers_evaluator():
    assert "triggers" in list_evaluators()
    ev = build_evaluator(
        "triggers",
        skill=_skill(),
        runtime=_ConstantRuntime("ok"),
        judge=HeuristicJudge(),
    )
    assert isinstance(ev, TriggerEvaluator)


# ── Scenario loader ──────────────────────────────────────────────────────


def _make_scenario(
    skill_dir: Path,
    *,
    scenario_name: str = "claims-denial",
    spec_extra: str = "",
    tasks: dict[str, str],
    fixtures: dict[str, str] | None = None,
) -> Path:
    """Build a complete scenario directory tree on disk."""
    scen = skill_dir / "evals" / "scenarios" / scenario_name
    scen.mkdir(parents=True)
    (scen / "spec.yaml").write_text(
        dedent(
            f"""\
            schema_version: bulbasaur/v1
            name: {scenario_name}
            skill_name: test-skill
            description: Scenario for tests.
            inputs:
              environment: production
            {spec_extra}
            """
        ),
        encoding="utf-8",
    )
    (scen / "tasks").mkdir()
    for filename, content in tasks.items():
        (scen / "tasks" / filename).write_text(dedent(content), encoding="utf-8")
    fixtures = fixtures or {}
    if fixtures:
        (scen / "fixtures").mkdir()
        for name, content in fixtures.items():
            (scen / "fixtures" / name).write_text(content, encoding="utf-8")
    return scen


def test_scenario_loader_returns_empty_when_directory_absent(tmp_path):
    assert load_scenarios(tmp_path) == []


def test_scenario_loader_parses_single_task(tmp_path):
    _make_scenario(
        tmp_path,
        tasks={
            "happy-path.yaml": """\
                id: task-001
                prompt: Restart deployment {{vars.environment}}.
                expected_output: A ValidationReport.
                assertions:
                  - Skill mentions kubectl
                  - Skill produces a ValidationReport
            """,
        },
    )
    suites = load_scenarios(tmp_path)
    assert len(suites) == 1
    suite = suites[0]
    assert suite.name == "scenario:claims-denial"
    assert suite.skill_name == "test-skill"
    assert len(suite.cases) == 1
    case = suite.cases[0]
    assert case.id == "task-001"
    # {{vars.environment}} substituted.
    assert "production" in case.prompt
    assert len(case.assertions) == 2


def test_scenario_loader_substitutes_fixture_content(tmp_path):
    _make_scenario(
        tmp_path,
        tasks={
            "with-fixture.yaml": """\
                id: t-001
                prompt: |
                  Process this:
                  {{fixture:input.txt}}
                assertions: []
            """,
        },
        fixtures={"input.txt": "FIXTURE-CONTENT-XYZ"},
    )
    suite = load_scenarios(tmp_path)[0]
    assert "FIXTURE-CONTENT-XYZ" in suite.cases[0].prompt


def test_scenario_loader_raises_on_missing_fixture(tmp_path):
    _make_scenario(
        tmp_path,
        tasks={
            "broken.yaml": """\
                id: t-001
                prompt: |
                  {{fixture:missing.txt}}
                assertions: []
            """,
        },
    )
    with pytest.raises(ScenarioLoadError) as exc:
        load_scenarios(tmp_path)
    assert "missing.txt" in exc.value.framework_error.summary


def test_scenario_loader_leaves_unknown_vars_in_place(tmp_path):
    """Unknown {{vars.foo}} should NOT crash; left in place so the author sees them."""
    _make_scenario(
        tmp_path,
        tasks={
            "t.yaml": """\
                id: t-001
                prompt: Use {{vars.unknown_key}} please.
                assertions: []
            """,
        },
    )
    suite = load_scenarios(tmp_path)[0]
    assert "{{vars.unknown_key}}" in suite.cases[0].prompt


def test_scenario_loader_rejects_missing_spec(tmp_path):
    scen = tmp_path / "evals" / "scenarios" / "no-spec"
    scen.mkdir(parents=True)
    (scen / "tasks").mkdir()
    with pytest.raises(ScenarioLoadError) as exc:
        load_scenarios(tmp_path)
    assert "spec.yaml" in exc.value.framework_error.summary


def test_scenario_loader_rejects_missing_tasks_dir(tmp_path):
    scen = tmp_path / "evals" / "scenarios" / "no-tasks"
    scen.mkdir(parents=True)
    (scen / "spec.yaml").write_text(
        "name: x\nskill_name: y\n", encoding="utf-8"
    )
    with pytest.raises(ScenarioLoadError) as exc:
        load_scenarios(tmp_path)
    assert "tasks/" in exc.value.framework_error.summary


def test_scenario_loader_rejects_task_without_prompt(tmp_path):
    _make_scenario(
        tmp_path,
        tasks={
            "broken.yaml": """\
                id: x
            """,
        },
    )
    with pytest.raises(ScenarioLoadError) as exc:
        load_scenarios(tmp_path)
    assert "prompt" in exc.value.framework_error.summary


def test_scenario_runner_integration(tmp_path):
    """End-to-end: EvalRunner picks up scenarios from evals/scenarios/."""
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: test\n---\nReply with: \"production-ack\"\n",
        encoding="utf-8",
    )
    _make_scenario(
        skill,
        scenario_name="simple",
        tasks={
            "t.yaml": """\
                id: t-001
                prompt: Acknowledge for {{vars.environment}}.
                assertions:
                  - response says production-ack
            """,
        },
    )
    config = EvalConfig(threshold=0.5)
    report = EvalRunner(skill, Strictness.LOCAL, config=config).run()
    # The scenario emerges as a suite named `scenario:simple`.
    scenario_suite = next(
        (s for s in report.suites if s.suite_name == "scenario:simple"), None
    )
    assert scenario_suite is not None
    assert scenario_suite.cases[0].case_id == "t-001"


# ── runner --baseline integration ────────────────────────────────────────


def test_runner_baseline_flag_wraps_evaluators(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: When asked, reply with foo.\n---\n"
        "Reply with: \"the skill answer matches\"\n",
        encoding="utf-8",
    )
    (skill / "evals").mkdir()
    (skill / "evals" / "behavior.json").write_text(
        json.dumps({
            "skill_name": "s",
            "evals": [{
                "id": 1,
                "prompt": "do x",
                "expected_output": "",
                "assertions": ["the skill answer matches"],
            }],
        }),
        encoding="utf-8",
    )
    config = EvalConfig(threshold=0.0)
    report = EvalRunner(
        skill, Strictness.LOCAL, config=config, baseline=True
    ).run()
    # The wrapped suite name carries `+baseline`.
    assert any("+baseline" in s.suite_name for s in report.suites)
