"""Unit tests for bbsctl skill-eval routing (Langflow stubbed)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "components"))

lfx = types.ModuleType("lfx")
lfx_custom = types.ModuleType("lfx.custom")
lfx_schema = types.ModuleType("lfx.schema")


class _StubComponent:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _StubMessage:
    def __init__(self, text: str = "", **kwargs):
        self.text = text
        self.data = kwargs


lfx_custom.Component = _StubComponent
lfx_schema.Message = _StubMessage
sys.modules["lfx"] = lfx
sys.modules["lfx.custom"] = lfx_custom
sys.modules["lfx.schema"] = lfx_schema

for name in list(sys.modules):
    if name.startswith("skill_eval"):
        del sys.modules[name]

from skill_eval.bbsctl_skill_eval import (  # noqa: E402
    BbsctlSkillEvalComponent,
    SkillEvalOutcome,
    SkillEvalRequest,
    run_skill_eval,
)


def _outcome(*, ok: bool, exit_code: int = 0, stdout: str = "", stderr: str = "") -> SkillEvalOutcome:
    return SkillEvalOutcome(
        ok=ok,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        report={"ok": ok} if ok else None,
    )


def test_pass_result_when_ok():
    component = BbsctlSkillEvalComponent(skill_dir="/tmp/skill", stage="compile", timeout_sec=5.0)
    with patch(
        "skill_eval.bbsctl_skill_eval.run_skill_eval",
        return_value=_outcome(ok=True, stdout='{"stage":"compile"}'),
    ) as mocked:
        passed = component.pass_result()
        failed = component.fail_result()
    mocked.assert_called_once()
    assert passed is not None
    assert passed.text == '{"stage":"compile"}'
    assert failed is None


def test_fail_result_when_not_ok():
    component = BbsctlSkillEvalComponent(skill_dir="/tmp/skill", stage="validate", timeout_sec=5.0)
    with patch(
        "skill_eval.bbsctl_skill_eval.run_skill_eval",
        return_value=_outcome(ok=False, exit_code=2, stderr="validation failed"),
    ) as mocked:
        passed = component.pass_result()
        failed = component.fail_result()
    mocked.assert_called_once()
    assert passed is None
    assert failed is not None
    assert failed.text == "validation failed"


def test_run_skill_eval_invokes_bbsctl_cli_boundary():
    req = SkillEvalRequest(skill_dir=Path("/tmp/example-skill"), stage="eval", timeout_sec=10.0)
    completed = MagicMock(returncode=0, stdout='{"passed":true}', stderr="")
    with (
        patch("skill_eval.bbsctl_skill_eval.shutil.which", return_value="/usr/bin/bbsctl"),
        patch("skill_eval.bbsctl_skill_eval.subprocess.run", return_value=completed) as run,
    ):
        outcome = run_skill_eval(req)
    assert outcome.ok is True
    assert outcome.report == {"passed": True}
    cmd = run.call_args.args[0]
    assert cmd[0] == "/usr/bin/bbsctl"
    assert cmd[1] == "eval"
    assert cmd[2].endswith("example-skill")


def test_run_skill_eval_falls_back_to_skillctl_module():
    req = SkillEvalRequest(skill_dir=Path("/tmp/example-skill"), stage="compile", timeout_sec=10.0)
    completed = MagicMock(returncode=1, stdout="", stderr="boom")
    with (
        patch("skill_eval.bbsctl_skill_eval.shutil.which", return_value=None),
        patch("skill_eval.bbsctl_skill_eval.subprocess.run", return_value=completed) as run,
    ):
        outcome = run_skill_eval(req)
    assert outcome.ok is False
    assert outcome.exit_code == 1
    cmd = run.call_args.args[0]
    assert cmd[:3] == ["python", "-m", "skillctl"]
    assert cmd[3] == "compile"


@pytest.mark.parametrize("stage", ["compile", "validate", "eval"])
def test_build_request_preserves_stage(stage: str):
    component = BbsctlSkillEvalComponent(skill_dir="/skills/demo", stage=stage, timeout_sec=30.0)
    req = component.build_request()
    assert req.stage == stage
    assert req.timeout_sec == 30.0
    assert req.skill_dir == Path("/skills/demo")
