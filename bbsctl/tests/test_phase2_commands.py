"""Integration tests for Phase 2 CLI commands."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from skillctl.cli import main


def _make_skill(tmp_path: Path, name: str = "my-skill", strictness: str = "local") -> Path:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Generates a report for the given input data.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    if strictness == "team":
        (skill_dir / "skill.yaml").write_text(
            f"name: {name}\nstrictness: team\n", encoding="utf-8"
        )
    return skill_dir


# ── bbsctl new --strictness team ─────────────────────────────────────────────

def test_new_team_creates_skill_yaml(tmp_path: Path) -> None:
    rc = main(["new", "team-skill", "--strictness", "team", "--dir", str(tmp_path)])
    assert rc == 0
    skill_dir = tmp_path / "team-skill"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "skill.yaml").exists()
    content = (skill_dir / "skill.yaml").read_text()
    assert "strictness: team" in content


def test_new_local_no_skill_yaml(tmp_path: Path) -> None:
    rc = main(["new", "local-skill", "--strictness", "local", "--dir", str(tmp_path)])
    assert rc == 0
    skill_dir = tmp_path / "local-skill"
    assert not (skill_dir / "skill.yaml").exists()


# ── bbsctl strictness team ────────────────────────────────────────────────────

def test_strictness_team_creates_skill_yaml(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, strictness="local")
    rc = main(["strictness", "team", str(skill_dir), "--yes"])
    assert rc == 0
    assert (skill_dir / "skill.yaml").exists()
    content = (skill_dir / "skill.yaml").read_text()
    assert "strictness: team" in content


def test_strictness_team_idempotent(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, strictness="team")
    rc = main(["strictness", "team", str(skill_dir), "--yes"])
    assert rc == 0


def test_strictness_team_missing_skill_md(tmp_path: Path) -> None:
    rc = main(["strictness", "team", str(tmp_path), "--yes"])
    assert rc == 1


# ── bbsctl validate --fast ────────────────────────────────────────────────────

def test_validate_fast_local_no_skill_yaml_passes(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path)
    rc = main(["validate", str(skill_dir), "--strictness", "local"])
    assert rc == 0


def test_validate_fast_team_no_skill_yaml_fails(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path)
    rc = main(["validate", str(skill_dir), "--strictness", "team"])
    assert rc == 1


def test_validate_fast_team_with_skill_yaml_passes(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, strictness="team")
    rc = main(["validate", str(skill_dir)])
    assert rc == 0


def test_validate_json_output(tmp_path: Path, capsys) -> None:
    skill_dir = _make_skill(tmp_path, strictness="team")
    rc = main(["validate", str(skill_dir), "--output", "json"])
    assert rc == 0
    import json
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["passed"] is True
    assert "validators" in data


# ── bbsctl init ───────────────────────────────────────────────────────────────

def test_init_adds_tool_bulbasaur(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'myproject'\n", encoding="utf-8")
    rc = main(["init", "--dir", str(tmp_path)])
    assert rc == 0
    content = (tmp_path / "pyproject.toml").read_text()
    assert "[tool.bulbasaur]" in content


def test_init_no_pyproject_fails(tmp_path: Path) -> None:
    rc = main(["init", "--dir", str(tmp_path)])
    assert rc == 1


def test_init_already_exists_skips(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'x'\n\n[tool.bulbasaur]\nversion = 1\n", encoding="utf-8"
    )
    rc = main(["init", "--dir", str(tmp_path)])
    assert rc == 0  # no error — skips gracefully


# ── bbsctl marketplace init ───────────────────────────────────────────────────

def test_marketplace_init_creates_structure(tmp_path: Path) -> None:
    mp_dir = tmp_path / "my-marketplace"
    rc = main(["marketplace", "init", str(mp_dir)])
    assert rc == 0
    assert (mp_dir / ".claude-plugin" / "marketplace.json").exists()


def test_marketplace_list_empty(tmp_path: Path) -> None:
    mp_dir = tmp_path / "my-marketplace"
    main(["marketplace", "init", str(mp_dir)])
    rc = main(["marketplace", "list", str(mp_dir)])
    assert rc == 0


# ── bbsctl publish --marketplace ─────────────────────────────────────────────

def test_publish_to_team_marketplace(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, strictness="team")
    mp_dir = tmp_path / "mp"
    main(["marketplace", "init", str(mp_dir)])
    rc = main(["publish", str(skill_dir), "--marketplace", str(mp_dir)])
    assert rc == 0
    plugins = [p for p in (mp_dir / "plugins").iterdir() if p.is_dir()]
    assert len(plugins) == 1


# ── bbsctl add / install / list / remove ─────────────────────────────────────

def test_add_and_list(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, strictness="team")
    mp_dir = tmp_path / "mp"
    main(["marketplace", "init", str(mp_dir)])
    main(["publish", str(skill_dir), "--marketplace", str(mp_dir)])

    project_dir = tmp_path / "consumer"
    project_dir.mkdir()
    rc = main(["add", f"my-skill-plugin@{mp_dir}", "--dir", str(project_dir)])
    assert rc == 0
    assert (project_dir / "skills.lock").exists()

    rc = main(["list", "--dir", str(project_dir)])
    assert rc == 0


def test_remove_skill(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, strictness="team")
    mp_dir = tmp_path / "mp"
    main(["marketplace", "init", str(mp_dir)])
    main(["publish", str(skill_dir), "--marketplace", str(mp_dir)])

    project_dir = tmp_path / "consumer"
    project_dir.mkdir()
    main(["add", f"my-skill-plugin@{mp_dir}", "--dir", str(project_dir)])

    rc = main(["remove", "my-skill-plugin", "--dir", str(project_dir)])
    assert rc == 0

    from skillctl.marketplace.lock import load_lock
    lock = load_lock(project_dir)
    assert lock.get_plugin("my-skill-plugin") is None
