"""bbsctl discover — ARD emit-only surface."""

from __future__ import annotations

import json
from pathlib import Path

from skillctl.cli import main
from skillctl.marketplace.ard import skill_to_ard_entry, write_ard_manifest


def test_skill_to_ard_entry(tmp_path: Path):
    skill = tmp_path / "log-helper"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: log-helper\ndescription: Analyze application logs for errors.\n---\n\n"
        "## When to use\n- User pastes a stack trace\n",
        encoding="utf-8",
    )
    entry = skill_to_ard_entry(skill, domain="example.com")
    assert entry["identifier"] == "urn:air:example.com:skill:log-helper"
    assert entry["type"] == "application/agent-skills+md"


def test_discover_cli(tmp_path: Path):
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: A tiny skill for ard emit.\n---\n\n# S\n",
        encoding="utf-8",
    )
    out = tmp_path / "ard.json"
    code = main(
        ["discover", str(skill), "--domain", "example.com", "-o", str(out)]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["entries"][0]["identifier"].endswith(":skill:s")


def test_ard_upsert_merges(tmp_path: Path):
    out = tmp_path / "ard.json"
    skill_a = tmp_path / "a"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text(
        "---\nname: a\ndescription: Skill a.\n---\n", encoding="utf-8"
    )
    skill_b = tmp_path / "b"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text(
        "---\nname: b\ndescription: Skill b.\n---\n", encoding="utf-8"
    )
    write_ard_manifest([skill_to_ard_entry(skill_a, domain="x.com")], out)
    write_ard_manifest([skill_to_ard_entry(skill_b, domain="x.com")], out, upsert=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert {e["displayName"] for e in data["entries"]} == {"a", "b"}
