"""Unit tests for MelleaEngine and bbsctl mellea-certify."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillctl.cli import main
from skillctl.lifecycle.config import MELLEA_INSTALL, MELLEA_PIN, LifecycleConfig
from skillctl.lifecycle.engines.mellea import (
    MelleaEngine,
    collect_audit,
    find_compiled_dir,
)
from skillctl.lifecycle.engines.base import StageContext
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.result import StageStatus
from skillctl.strictness import Strictness


def _skill(tmp_path: Path, name: str = "s") -> Path:
    skill = tmp_path / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: mellea test skill\n---\n",
        encoding="utf-8",
    )
    return skill


def _ctx(skill: Path, *, strictness: Strictness = Strictness.TEAM) -> StageContext:
    return StageContext(
        skill_dir=skill,
        stage=Stage.CERTIFY,
        strictness=strictness,
        config=LifecycleConfig(),
        use_cache=False,
    )


def test_engines_group_pins_mellea_compiler():
    """Optional engines group must pin mellea-skills-compiler at MELLEA_PIN."""
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert "mellea-skills-compiler" in text
    assert MELLEA_PIN in text
    assert MELLEA_PIN in MELLEA_INSTALL


def test_find_compiled_dir_prefers_sibling(tmp_path: Path):
    skill = _skill(tmp_path, "demo")
    sibling = tmp_path / "demo_mellea"
    sibling.mkdir()
    assert find_compiled_dir(skill) == sibling


def test_find_compiled_dir_nested(tmp_path: Path):
    skill = _skill(tmp_path, "demo")
    nested = skill / "demo_mellea"
    nested.mkdir()
    assert find_compiled_dir(skill) == nested


def test_find_compiled_dir_missing(tmp_path: Path):
    skill = _skill(tmp_path)
    assert find_compiled_dir(skill) is None


def test_collect_audit_copies_known_files(tmp_path: Path):
    skill = _skill(tmp_path)
    compiled = tmp_path / "s_mellea"
    audit = compiled / "audit"
    audit.mkdir(parents=True)
    (audit / "CERTIFICATION.md").write_text("# ok\n", encoding="utf-8")
    (audit / "policy_manifest.json").write_text("{}", encoding="utf-8")
    (audit / "ignored.txt").write_text("nope\n", encoding="utf-8")

    artifacts = collect_audit(compiled, skill)
    assert "certification/CERTIFICATION.md" in artifacts
    assert "certification/policy_manifest.json" in artifacts
    assert "certification/ignored.txt" not in artifacts
    dest = skill / "dist" / "certification" / "CERTIFICATION.md"
    assert dest.read_text(encoding="utf-8") == "# ok\n"


def test_mellea_engine_missing_binary(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("skillctl.lifecycle.engines.mellea.shutil.which", lambda _: None)
    engine = MelleaEngine()
    assert engine.available() is False
    result = engine.run(_ctx(_skill(tmp_path)))
    assert result.status == StageStatus.ERROR
    assert "not on PATH" in result.detail
    assert result.engine.name == "mellea"
    assert result.engine.revision == MELLEA_PIN


def test_mellea_engine_compile_failure(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "skillctl.lifecycle.engines.mellea.shutil.which", lambda _: "/bin/mellea-skills"
    )

    def boom(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stderr="compile blew up", stdout="")

    monkeypatch.setattr("skillctl.lifecycle.engines.mellea._run", boom)
    result = MelleaEngine().run(_ctx(_skill(tmp_path)))
    assert result.status == StageStatus.ERROR
    assert "compile blew up" in result.detail


def test_mellea_engine_certify_success_and_enforce(monkeypatch, tmp_path: Path):
    skill = _skill(tmp_path, "demo")
    compiled = tmp_path / "demo_mellea"
    audit = compiled / "audit"
    audit.mkdir(parents=True)
    (audit / "CERTIFICATION.md").write_text("pass\n", encoding="utf-8")

    monkeypatch.setattr(
        "skillctl.lifecycle.engines.mellea.shutil.which", lambda _: "/bin/mellea-skills"
    )
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        return SimpleNamespace(returncode=0, stderr="", stdout="ok")

    monkeypatch.setattr("skillctl.lifecycle.engines.mellea._run", fake_run)

    result = MelleaEngine().run(_ctx(skill, strictness=Strictness.REGULATED))
    assert result.status == StageStatus.PASSED
    assert result.engine.name == "mellea"
    assert "certification/CERTIFICATION.md" in result.artifacts
    assert seen[0][:2] == ["mellea-skills", "compile"]
    assert seen[1][:2] == ["mellea-skills", "certify"]
    assert "--enforce" in seen[1]


def test_mellea_certify_cli_missing_binary_mentions_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    skill = _skill(tmp_path)
    code = main(["mellea-certify", str(skill), "--output", "json"])
    assert code == 2
    err = capsys.readouterr().err
    assert "mellea" in err.lower()
    assert "mellea-certify" in err
    assert "uv tool install" in err or "uv sync" in err


def test_mellea_certify_forces_mellea_despite_config_none(
    tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
):
    """mellea-certify ignores certify=none and always uses MelleaEngine."""
    skill = _skill(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[tool.bbsctl.engines]\ncertify = \"none\"\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(MelleaEngine, "available", lambda self: True)

    def fake_run(self, ctx):
        from skillctl.lifecycle.result import EngineInfo, StageResult

        return StageResult(
            stage=Stage.CERTIFY.value,
            status=StageStatus.PASSED,
            engine=EngineInfo(name="mellea", revision=MELLEA_PIN),
            detail="forced",
        )

    monkeypatch.setattr(MelleaEngine, "run", fake_run)

    code = main(["mellea-certify", str(skill), "--no-cache", "--output", "json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["stage"] == "certify"
    assert data["engine"]["name"] == "mellea"
    assert data["status"] == "passed"


def test_certify_config_none_does_not_invoke_mellea(
    tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
):
    """bbsctl certify with default certify=none must not require mellea-skills."""
    skill = _skill(tmp_path)
    called = {"mellea": False}

    def mark_available(self):
        called["mellea"] = True
        return False

    monkeypatch.setattr(MelleaEngine, "available", mark_available)

    code = main(["certify", str(skill), "--output", "json"])
    # none engine reports unavailable → exit 2, but Mellea must not be selected
    assert called["mellea"] is False
    assert code == 2
    err = capsys.readouterr().err
    assert "none" in err.lower() or "not available" in err.lower()
