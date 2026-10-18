"""Behavior tests for bbsctl lifecycle (pipeline / doctor / evidence)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillctl.cli import main
from skillctl.lifecycle.cache import cache_root
from skillctl.lifecycle.config import LifecycleConfig
from skillctl.lifecycle.pipeline import (
    Stage,
    plan_for_strictness,
    resume_fix,
    Runner,
)
from skillctl.lifecycle.result import StageResult, StageStatus
from skillctl.strictness import Strictness


SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "pr-review-helper"


def test_project_scripts_only_bbsctl():
    """Single console script — lifecycle is not a second binary."""
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert 'bbsctl = "skillctl.cli:main"' in text
    assert "skillops =" not in text.split("[project.scripts]")[1].split("[")[0]


def test_plan_team_requires_scan():
    plan = plan_for_strictness(Strictness.TEAM)
    by_name = {s.stage: s.required for s in plan.stages}
    assert by_name[Stage.COMPILE] is True
    assert by_name[Stage.SCAN] is True


def test_run_fail_fast_on_stage_failure(tmp_path: Path):
    """Runner stops at the first failed stage and does not call later engines."""

    class Boom:
        name = "boom"

        def available(self) -> bool:
            return True

        def version(self) -> str:
            return "1"

        def install_fix(self) -> str:
            return "n/a"

        def run(self, ctx):
            return StageResult(
                stage=ctx.stage.value,
                status=StageStatus.FAILED,
                detail="boom",
            )

    class Never:
        name = "never"
        called = False

        def available(self) -> bool:
            return True

        def version(self) -> str:
            return "1"

        def install_fix(self) -> str:
            return "n/a"

        def run(self, ctx):
            Never.called = True
            return StageResult(stage=ctx.stage.value, status=StageStatus.PASSED)

    from skillctl.lifecycle.config import LifecycleConfig

    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: s\ndescription: x\n---\n", encoding="utf-8")

    plan = plan_for_strictness(Strictness.LOCAL)
    # Force compile → scan order with compile failing
    engines = {Stage.COMPILE: Boom(), Stage.SCAN: Never(), Stage.EVAL: Never()}
    report = Runner(
        skill_dir=skill,
        config=LifecycleConfig(),
        engines=engines,
        use_cache=False,
    ).run(plan)

    assert report.exit_code == 1
    assert report.results[0].stage == "compile"
    assert report.results[0].status == StageStatus.FAILED
    assert Never.called is False


def test_doctor_via_cli(capsys):
    code = main(["doctor", "--output", "json"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    names = {row["name"] for row in out}
    assert "bbsctl" in names


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="sample skill missing")
def test_scan_standalone_on_sample(capsys):
    """Legacy bbsctl scan always uses bbsctl-audit."""
    code = main(
        [
            "scan",
            str(SAMPLE),
            "--strictness",
            "local",
            "--no-cache",
            "--output",
            "json",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["stage"] == "scan"
    assert data["status"] == "passed"
    assert data["engine"]["name"] == "bbsctl-audit"


def test_inspect_requires_skillspector(tmp_path: Path, capsys):
    """bbsctl inspect always targets NVIDIA SkillSpector."""
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: inspect target skill\n---\n",
        encoding="utf-8",
    )
    code = main(["inspect", str(skill), "--output", "json"])
    # Without skillspector on PATH → exit 2 (engine missing)
    assert code == 2


def test_help_lists_stage_commands():
    """Independent stage commands are registered on bbsctl."""
    from skillctl.cli import _build_parser

    parser = _build_parser()
    # argparse stores subparsers on the parser
    actions = [a for a in parser._actions if getattr(a, "dest", None) == "command"]
    assert actions
    names = set(actions[0].choices.keys())
    for required in (
        "inspect",
        "scan",
        "mellea-certify",
        "certify",
        "pipeline",
        "approve",
        "verify",
        "doctor",
        "compile",
        "eval",
        "publish",
        "discover",
    ):
        assert required in names


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="sample skill missing")
def test_pipeline_fast_on_sample(capsys):
    code = main(
        [
            "pipeline",
            str(SAMPLE),
            "--fast",
            "--strictness",
            "local",
            "--no-cache",
            "--output",
            "json",
        ]
    )
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    stages = [r["stage"] for r in data["results"]]
    assert stages == ["compile"]
    assert data["results"][0]["status"] == "passed"


def test_approve_and_verify_roundtrip(tmp_path: Path, capsys):
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: a test skill for approve\n---\n\n# S\n",
        encoding="utf-8",
    )
    assert main(["approve", str(skill), "--by", "tester"]) == 0
    assert main(["verify", str(skill)]) == 0


def test_resume_fix_mentions_from_stage():
    hint = resume_fix(Stage.SCAN)
    assert "--from scan" in hint
    assert "stage cache" in hint


def test_pipeline_does_not_cache_error_results(tmp_path: Path, monkeypatch):
    """Failed/error stages must not land in the stage cache."""

    class ErrEngine:
        name = "err"

        def available(self) -> bool:
            return True

        def version(self) -> str:
            return "1"

        def install_fix(self) -> str:
            return "n/a"

        def run(self, ctx):
            return StageResult(
                stage=ctx.stage.value,
                status=StageStatus.ERROR,
                detail="subprocess crashed",
            )

    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: cache miss skill\n---\n", encoding="utf-8"
    )

    plan = plan_for_strictness(Strictness.LOCAL)
    report = Runner(
        skill_dir=skill,
        config=LifecycleConfig(),
        engines={Stage.COMPILE: ErrEngine()},
        use_cache=True,
    ).run(plan, to_stage=Stage.COMPILE)

    assert report.exit_code == 2
    # No JSON files under the lifecycle cache for this run.
    root = cache_root()
    if root.exists():
        assert list(root.rglob("*.json")) == []
