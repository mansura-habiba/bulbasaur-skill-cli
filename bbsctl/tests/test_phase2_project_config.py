"""Tests for project_config.py (Phase 2 — ADR 0007)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from skillctl.project_config import ProjectConfig, load_project_config, render_toml_section
from skillctl.strictness import Strictness


def _write_pyproject(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_no_pyproject_returns_defaults(tmp_path: Path) -> None:
    cfg = load_project_config(tmp_path)
    assert cfg.default_strictness == Strictness.LOCAL
    assert cfg.marketplace is None


def test_pyproject_without_bulbasaur_section(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, """\
        [project]
        name = "myproject"
    """)
    cfg = load_project_config(tmp_path)
    assert cfg.default_strictness == Strictness.LOCAL


def test_bulbasaur_section_parsed(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, """\
        [tool.bulbasaur]
        version = 1
        default_strictness = "team"
        marketplace = "./my-marketplace"
    """)
    cfg = load_project_config(tmp_path)
    assert cfg.default_strictness == Strictness.TEAM
    assert cfg.marketplace == "./my-marketplace"


def test_spec_lint_policy_parsed(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, """\
        [tool.bulbasaur]
        version = 1
        default_strictness = "local"

        [tool.bulbasaur.spec_lint]
        local = "skip"
        team = "block"
    """)
    cfg = load_project_config(tmp_path)
    assert cfg.spec_lint.local == "skip"
    assert cfg.spec_lint.team == "block"
    assert cfg.spec_lint.org == "block"   # default


def test_load_from_subdirectory(tmp_path: Path) -> None:
    """Config should be found when searching from a child dir."""
    _write_pyproject(tmp_path, """\
        [tool.bulbasaur]
        version = 1
        default_strictness = "team"
    """)
    skill_dir = tmp_path / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    cfg = load_project_config(skill_dir)
    assert cfg.default_strictness == Strictness.TEAM


def test_render_toml_section_roundtrip(tmp_path: Path) -> None:
    import tomllib
    config = ProjectConfig(
        default_strictness=Strictness.TEAM,
        marketplace="./my-mp",
    )
    snippet = render_toml_section(config)
    # Should parse as valid TOML when wrapped in a [project] context.
    full_toml = "[project]\nname = 'x'\n" + snippet
    parsed = tomllib.loads(full_toml)
    assert parsed["tool"]["bulbasaur"]["default_strictness"] == "team"
