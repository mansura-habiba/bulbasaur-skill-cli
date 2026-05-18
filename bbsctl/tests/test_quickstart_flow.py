"""End-to-end test of the quickstart flow.

This is the test the DX charter's five-minute promise rests on. If this regresses,
the framework regresses. CI's `quickstart-smoke.yml` runs the shell version of
this against a fresh install; this Python test runs the same flow against the
in-tree code so unit-test regressions surface immediately.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from skillctl.cli import main as cli_main


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_new_creates_valid_skill(workspace):
    exit_code = cli_main(["new", "hello-skill"])
    assert exit_code == 0

    skill_md = workspace / "hello-skill" / "SKILL.md"
    assert skill_md.exists()

    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: hello-skill" in text
    assert "description:" in text


def test_new_then_compile(workspace):
    assert cli_main(["new", "hello-skill"]) == 0
    assert cli_main(["compile", "hello-skill"]) == 0

    report = workspace / "hello-skill" / "dist" / "compile-report.json"
    assert report.exists()

    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["strictness"] == "local"
    assert data["frontmatter"]["name"] == "hello-skill"
    step_names = [s["name"] for s in data["steps"]]
    assert "parse-frontmatter" in step_names
    assert "validate-agentskills-spec" in step_names
    assert "emit-report" in step_names
    for step in data["steps"]:
        assert step["outcome"] in {"ok", "skipped"}


def test_new_compile_run_quickstart_hello_skill(workspace, capsys):
    # The four-line hello-skill in quickstart/ should compile and run cleanly.
    skill_md_text = (
        "---\n"
        "name: hello-skill\n"
        "description: Reply with a friendly greeting when the user says hello.\n"
        "---\n"
        "\n"
        'Reply with: "Hello! I\'m the hello-skill — your first Bulbasaur skill."\n'
    )
    skill_dir = workspace / "hello-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(skill_md_text, encoding="utf-8")

    assert cli_main(["compile", "hello-skill"]) == 0

    capsys.readouterr()  # clear
    assert cli_main(["run", "hello-skill"]) == 0
    captured = capsys.readouterr()
    assert "Hello! I'm the hello-skill" in captured.out


def test_compile_emits_error_with_fix_for_bad_name(workspace, capsys):
    skill_dir = workspace / "Bad-Name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Bad-Name\ndescription: x\n---\n", encoding="utf-8"
    )
    code = cli_main(["compile", "Bad-Name"])
    captured = capsys.readouterr()
    assert code != 0
    # Error-message contract: every user-facing error must carry a Fix line.
    combined = captured.out + captured.err
    assert "ERROR:" in combined
    assert "Fix:" in combined
