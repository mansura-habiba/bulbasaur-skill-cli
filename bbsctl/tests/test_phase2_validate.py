"""Tests for the Phase 2 validate module."""

from __future__ import annotations

import textwrap
from pathlib import Path

from skillctl.validate import ValidateMode, ValidateRunner
from skillctl.strictness import Strictness


def _write(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _make_skill(tmp_path: Path, *, name: str = "my-skill", description: str | None = None) -> Path:
    desc = description or f"Generates a comprehensive {name} report for the given input."
    skill_md = f"---\nname: {name}\ndescription: {desc}\n---\n\n# Body\n"
    _write(tmp_path / "SKILL.md", skill_md)
    return tmp_path


# ── EnterpriseSpecValidator ───────────────────────────────────────────────────

def test_no_skill_yaml_at_local_passes(tmp_path: Path) -> None:
    _make_skill(tmp_path)
    runner = ValidateRunner(tmp_path, Strictness.LOCAL)
    result = runner.run()
    # enterprise-spec warns but should not fail at local without skill.yaml
    assert result.passed


def test_no_skill_yaml_at_team_fails(tmp_path: Path) -> None:
    _make_skill(tmp_path)
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    assert not result.passed
    errors = [e for r in result.results for e in r.errors]
    assert any("skill.yaml" in e.summary for e in errors)


def test_valid_team_skill_yaml_passes(tmp_path: Path) -> None:
    _make_skill(tmp_path)
    _write(tmp_path / "skill.yaml", "name: my-skill\nstrictness: team\n")
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    assert result.passed


# ── BasicTriggerValidator ─────────────────────────────────────────────────────

def test_generic_name_warns(tmp_path: Path) -> None:
    _make_skill(tmp_path, name="helper",
                description="Generates a report when the user needs help with something.")
    _write(tmp_path / "skill.yaml", "name: helper\nstrictness: team\n")
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    warnings = [w for r in result.results for w in r.warnings]
    assert any("generic" in w.summary for w in warnings)


def test_short_description_fails(tmp_path: Path) -> None:
    _make_skill(tmp_path, description="Too short")
    _write(tmp_path / "skill.yaml", "name: my-skill\nstrictness: team\n")
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    assert not result.passed
    errors = [e for r in result.results for e in r.errors]
    assert any("too short" in e.summary for e in errors)


def test_good_description_passes(tmp_path: Path) -> None:
    _make_skill(
        tmp_path,
        name="incident-triage",
        description="Triages incoming production incidents by severity and generates an initial runbook entry.",
    )
    _write(tmp_path / "skill.yaml", "name: incident-triage\nstrictness: team\n")
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    assert result.passed


# ── OutputContractValidator ───────────────────────────────────────────────────

def test_no_output_contract_passes(tmp_path: Path) -> None:
    _make_skill(tmp_path)
    _write(tmp_path / "skill.yaml", "name: my-skill\nstrictness: team\n")
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    assert result.passed


def test_valid_output_contract_passes(tmp_path: Path) -> None:
    _make_skill(tmp_path)
    _write(tmp_path / "skill.yaml", """\
        name: my-skill
        strictness: team
        output_contract:
          output:
            type: object
            properties:
              summary:
                type: string
    """)
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    assert result.passed


def test_invalid_output_contract_type_fails(tmp_path: Path) -> None:
    _make_skill(tmp_path)
    _write(tmp_path / "skill.yaml", """\
        name: my-skill
        strictness: team
        output_contract:
          output:
            type: not-a-real-type
    """)
    runner = ValidateRunner(tmp_path, Strictness.TEAM)
    result = runner.run()
    assert not result.passed


# ── JSON output ───────────────────────────────────────────────────────────────

def test_validate_result_has_expected_fields(tmp_path: Path) -> None:
    _make_skill(tmp_path)
    _write(tmp_path / "skill.yaml", "name: my-skill\nstrictness: team\n")
    runner = ValidateRunner(tmp_path, Strictness.TEAM, mode=ValidateMode.FAST)
    result = runner.run()
    assert result.mode == ValidateMode.FAST
    assert result.skill_dir == tmp_path
    validator_names = [r.validator_name for r in result.results]
    assert "enterprise-spec" in validator_names
    assert "basic-trigger" in validator_names
    assert "output-contract" in validator_names
