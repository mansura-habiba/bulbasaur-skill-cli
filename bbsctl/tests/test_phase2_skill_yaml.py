"""Tests for skill.yaml parsing (Phase 2)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from skillctl.skill_yaml import (
    SkillOverlay,
    SkillYamlError,
    load_skill_yaml,
    write_skill_yaml,
)
from skillctl.strictness import Strictness


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "skill.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ── load_skill_yaml ──────────────────────────────────────────────────────────

def test_absent_returns_none(tmp_path: Path) -> None:
    assert load_skill_yaml(tmp_path) is None


def test_minimal_team_overlay(tmp_path: Path) -> None:
    _write(tmp_path, """\
        name: my-skill
        strictness: team
        version: 0.2.0
    """)
    overlay = load_skill_yaml(tmp_path)
    assert overlay is not None
    assert overlay.name == "my-skill"
    assert overlay.strictness == Strictness.TEAM
    assert overlay.version == "0.2.0"


def test_missing_name_raises(tmp_path: Path) -> None:
    _write(tmp_path, "strictness: team\n")
    with pytest.raises(SkillYamlError) as exc_info:
        load_skill_yaml(tmp_path)
    assert "name" in exc_info.value.framework_error.summary


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    (tmp_path / "skill.yaml").write_text("key: : bad\n", encoding="utf-8")
    with pytest.raises(SkillYamlError):
        load_skill_yaml(tmp_path)


def test_ownership_parsed(tmp_path: Path) -> None:
    _write(tmp_path, """\
        name: owned-skill
        strictness: team
        ownership:
          team: platform-eng
          contact: platform@example.com
    """)
    overlay = load_skill_yaml(tmp_path)
    assert overlay is not None
    assert overlay.has_ownership
    assert overlay.ownership.team == "platform-eng"  # type: ignore[union-attr]


def test_output_contract_parsed(tmp_path: Path) -> None:
    _write(tmp_path, """\
        name: oc-skill
        strictness: team
        output_contract:
          output:
            type: object
            properties:
              summary:
                type: string
    """)
    overlay = load_skill_yaml(tmp_path)
    assert overlay is not None
    assert overlay.output_contract is not None
    assert overlay.output_contract.output["type"] == "object"


def test_extra_keys_preserved(tmp_path: Path) -> None:
    _write(tmp_path, """\
        name: extra-skill
        strictness: local
        my_custom_field: hello
    """)
    overlay = load_skill_yaml(tmp_path)
    assert overlay is not None
    assert overlay.extra.get("my_custom_field") == "hello"


# ── write_skill_yaml round-trip ───────────────────────────────────────────────

def test_write_and_reload(tmp_path: Path) -> None:
    overlay = SkillOverlay(
        name="round-trip",
        strictness=Strictness.TEAM,
        version="1.2.3",
    )
    write_skill_yaml(tmp_path / "skill.yaml", overlay)
    reloaded = load_skill_yaml(tmp_path)
    assert reloaded is not None
    assert reloaded.name == "round-trip"
    assert reloaded.strictness == Strictness.TEAM
    assert reloaded.version == "1.2.3"
