"""Tests for the AI-assisted authoring path — composer + CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillctl.authoring import (
    AuthoringError,
    AuthoringRequest,
    SkillArchetype,
    author_skill,
)
from skillctl.commands import author_cmd
from skillctl.llm.base import LLMBackend, LLMBackendError, LLMResponse
from skillctl.skill_yaml import (
    RiskLevel,
    SkillOverlay,
    load_skill_yaml,
)
from skillctl.strictness import Strictness


# ── helpers ──────────────────────────────────────────────────────────────


class _StubBackend(LLMBackend):
    """Returns queued responses verbatim; tracks calls."""

    name = "stub"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise LLMBackendError("no more stubbed responses")
        item = self._responses.pop(0)
        if isinstance(item, LLMBackendError):
            raise item
        return LLMResponse(
            text=item,
            model=kwargs.get("model") or "stub-model",
            backend=self.name,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=12,
        )


def _envelope(
    description: str = "When the user asks to do a thing, the skill activates.",
    body: str = (
        "# Test Skill\n\n## When to reach for this skill\n\n- always\n\n"
        "## Inputs expected\n\n- prompt\n\n## Workflow\n\n1. respond\n\n"
        "## Outputs\n\n- a string\n"
    ),
    n_cases: int = 3,
) -> str:
    cases = [
        {
            "id": i,
            "prompt": f"prompt {i}",
            "expected_output": f"output {i}",
            "assertions": [f"asserts {i}"],
        }
        for i in range(1, n_cases + 1)
    ]
    return json.dumps(
        {"description": description, "body": body, "eval_cases": cases}
    )


# ── composer: validation ─────────────────────────────────────────────────


def test_composer_rejects_invalid_name(tmp_path):
    req = AuthoringRequest(
        name="BadName",  # camelCase — agentskills rule violation
        intent="do a thing",
        output_dir=tmp_path,
    )
    with pytest.raises(AuthoringError, match="invalid skill name"):
        author_skill(req, backend=_StubBackend([_envelope()]))


def test_composer_rejects_empty_intent(tmp_path):
    req = AuthoringRequest(
        name="my-skill",
        intent="   ",
        output_dir=tmp_path,
    )
    with pytest.raises(AuthoringError, match="intent is required"):
        author_skill(req, backend=_StubBackend([_envelope()]))


def test_composer_refuses_to_overwrite_existing_dir(tmp_path):
    (tmp_path / "my-skill").mkdir()
    req = AuthoringRequest(
        name="my-skill", intent="do x", output_dir=tmp_path
    )
    with pytest.raises(AuthoringError, match="refusing to overwrite"):
        author_skill(req, backend=_StubBackend([_envelope()]))


# ── composer: happy path with LLM ────────────────────────────────────────


def test_composer_writes_skill_md_at_local(tmp_path):
    req = AuthoringRequest(
        name="my-skill", intent="do x", output_dir=tmp_path
    )
    result = author_skill(req, backend=_StubBackend([_envelope()]))

    skill_md = result.skill_dir / "SKILL.md"
    assert skill_md.exists()
    text = skill_md.read_text(encoding="utf-8")
    assert "name: my-skill" in text
    assert "# Test Skill" in text
    # At local strictness, no skill.yaml or permissions.yaml.
    assert not (result.skill_dir / "skill.yaml").exists()
    assert not (result.skill_dir / "permissions.yaml").exists()


def test_composer_writes_evals_behavior_json(tmp_path):
    req = AuthoringRequest(
        name="my-skill", intent="do x", output_dir=tmp_path
    )
    result = author_skill(req, backend=_StubBackend([_envelope(n_cases=4)]))

    evals = result.skill_dir / "evals" / "behavior.json"
    assert evals.exists()
    data = json.loads(evals.read_text())
    assert data["skill_name"] == "my-skill"
    assert len(data["evals"]) == 4
    assert data["evals"][0]["prompt"] == "prompt 1"


def test_composer_writes_skill_yaml_at_team(tmp_path):
    req = AuthoringRequest(
        name="my-skill",
        intent="do x",
        output_dir=tmp_path,
        strictness=Strictness.TEAM,
        archetype=SkillArchetype.ANALYTICAL,
    )
    result = author_skill(req, backend=_StubBackend([_envelope()]))

    skill_yaml = result.skill_dir / "skill.yaml"
    perms = result.skill_dir / "permissions.yaml"
    assert skill_yaml.exists()
    assert perms.exists()
    overlay = load_skill_yaml(result.skill_dir)
    assert overlay.name == "my-skill"
    assert overlay.strictness == Strictness.TEAM


def test_composer_records_risk_level_in_skill_yaml(tmp_path):
    req = AuthoringRequest(
        name="my-skill",
        intent="do x",
        output_dir=tmp_path,
        strictness=Strictness.TEAM,
        archetype=SkillArchetype.DEVOPS,
        risk_level=RiskLevel.HIGH,
    )
    result = author_skill(req, backend=_StubBackend([_envelope()]))
    overlay = load_skill_yaml(result.skill_dir)
    assert overlay.risk.level == RiskLevel.HIGH
    # Devops archetype → side_effects=external by default; requires_human_approval=true.
    assert overlay.risk.requires_human_approval is True


def test_composer_devops_archetype_templates_kubectl_permissions(tmp_path):
    req = AuthoringRequest(
        name="restart-deploy",
        intent="restart mq deployments",
        output_dir=tmp_path,
        strictness=Strictness.TEAM,
        archetype=SkillArchetype.DEVOPS,
    )
    result = author_skill(req, backend=_StubBackend([_envelope()]))
    perms = (result.skill_dir / "permissions.yaml").read_text()
    assert "kubectl get" in perms
    assert "kube-system" in perms  # excluded by default
    assert "kubectl exec" in perms  # listed under deny


def test_composer_analytical_archetype_templates_readonly_permissions(tmp_path):
    req = AuthoringRequest(
        name="x", intent="summarize", output_dir=tmp_path,
        strictness=Strictness.TEAM,
        archetype=SkillArchetype.ANALYTICAL,
    )
    result = author_skill(req, backend=_StubBackend([_envelope()]))
    perms = (result.skill_dir / "permissions.yaml").read_text()
    assert "default: deny" in perms
    # Analytical has no kubectl allows.
    assert "kubectl" not in perms


# ── composer: fallback ────────────────────────────────────────────────────


def test_composer_falls_back_to_skeleton_on_backend_error(tmp_path):
    backend = _StubBackend([LLMBackendError("ollama unreachable")])
    req = AuthoringRequest(
        name="my-skill", intent="do x", output_dir=tmp_path
    )
    result = author_skill(req, backend=backend)
    assert result.fell_back_to_skeleton
    text = (result.skill_dir / "SKILL.md").read_text()
    assert "[draft]" in text


def test_composer_falls_back_when_response_unparseable(tmp_path):
    # First response is unparseable; retry response also unparseable.
    backend = _StubBackend(["not json at all", "still not json"])
    req = AuthoringRequest(
        name="my-skill", intent="do x", output_dir=tmp_path
    )
    result = author_skill(req, backend=backend)
    assert result.fell_back_to_skeleton
    # Two attempts were made.
    assert len(backend.calls) == 2


def test_composer_retries_on_first_unparseable_response(tmp_path):
    """First response is garbage; retry response is good."""
    backend = _StubBackend(["garbage", _envelope()])
    req = AuthoringRequest(
        name="my-skill", intent="do x", output_dir=tmp_path
    )
    result = author_skill(req, backend=backend)
    assert not result.fell_back_to_skeleton
    text = (result.skill_dir / "SKILL.md").read_text()
    assert "[draft]" not in text
    assert len(backend.calls) == 2


def test_composer_extracts_embedded_json_from_prose(tmp_path):
    """LLM wraps JSON in prose — composer should still find it."""
    envelope = _envelope()
    backend = _StubBackend([f"Sure! Here's the JSON:\n\n{envelope}\n\nLet me know."])
    req = AuthoringRequest(
        name="my-skill", intent="do x", output_dir=tmp_path
    )
    result = author_skill(req, backend=backend)
    assert not result.fell_back_to_skeleton


# ── CLI integration ──────────────────────────────────────────────────────


class _Args:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_cli_returns_1_on_invalid_name(capsys, tmp_path):
    rc = author_cmd.run(
        _Args(
            name="BadName",
            intent="do x",
            dir=str(tmp_path),
            strictness="local",
            archetype="analytical",
            risk_level=None,
            backend=None,
            model=None,
        )
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid skill name" in captured.err


def test_cli_registers_in_subparsers():
    from skillctl.cli import _build_parser

    parser = _build_parser()
    sub_actions = [
        a for a in parser._actions
        if hasattr(a, "choices") and isinstance(a.choices, dict)
    ]
    assert "author" in sub_actions[0].choices


def test_skill_archetype_from_string_tolerant():
    assert SkillArchetype.from_string("DEVOPS") == SkillArchetype.DEVOPS
    assert SkillArchetype.from_string(None) == SkillArchetype.ANALYTICAL
    assert SkillArchetype.from_string("not-a-thing") == SkillArchetype.ANALYTICAL


def test_authoring_request_defaults():
    req = AuthoringRequest(
        name="my-skill",
        intent="do x",
        output_dir=Path("/tmp"),
    )
    assert req.strictness == Strictness.LOCAL
    assert req.archetype == SkillArchetype.ANALYTICAL
    assert req.risk_level is None
