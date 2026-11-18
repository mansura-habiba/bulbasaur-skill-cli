from __future__ import annotations

import json
from pathlib import Path

from skillctl.cli import main
from skillctl.permissions.side_effects import OpKind, SideEffectCeiling
from skillctl.strictness import Strictness

_SKILL_MD = """\
---
name: review-notes
description: Reviews pull requests for risky changes and missing tests.
---

Read the diff and summarize risk.
"""

_CLOSED = """\
schema_version: bulbasaur/v1
skill: review-notes
commands:
  default: deny
network:
  default: deny
mcp_tools:
  default: deny
filesystem:
  write_paths: []
"""

_WRITE_GRANT = """\
schema_version: bulbasaur/v1
skill: review-notes
commands:
  default: deny
network:
  default: deny
mcp_tools:
  default: deny
filesystem:
  write_paths: ["out/*"]
"""


def _write_skill(
    tmp_path: Path,
    *,
    skill_yaml: str,
    permissions: str | None = None,
) -> Path:
    skill = tmp_path / "review-notes"
    skill.mkdir()
    (skill / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    (skill / "skill.yaml").write_text(skill_yaml, encoding="utf-8")
    if permissions is not None:
        (skill / "permissions.yaml").write_text(permissions, encoding="utf-8")
    return skill


def _read_only_yaml(*, token: str = "read_only") -> str:
    return (
        "name: review-notes\n"
        "strictness: local\n"
        "version: 1.0.0\n"
        "risk:\n"
        "  level: low\n"
        f"  side_effects: {token}\n"
    )


def _side_effects_block(payload: dict) -> dict:
    for validator in payload["validators"]:
        if validator["name"] == "side-effects":
            return validator
    raise AssertionError("side-effects validator did not run")


def test_validate_fails_when_permissions_exceed_declaration(tmp_path: Path, capsys) -> None:
    skill = _write_skill(
        tmp_path,
        skill_yaml=_read_only_yaml(),
        permissions=_WRITE_GRANT,
    )
    rc = main(["validate", str(skill), "--output", "json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    errors = _side_effects_block(payload)["errors"]
    assert errors
    detail = errors[0]["detail"] or ""
    assert "declared=read_only" in detail
    assert "implied=reversible" in detail


def test_ceiling_denies_write_under_read_only(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path,
        skill_yaml=_read_only_yaml(),
        permissions=_WRITE_GRANT,
    )
    ceiling = SideEffectCeiling.for_skill(skill, Strictness.LOCAL)
    write = ceiling.evaluate(OpKind.WRITE, "out/x")
    read = ceiling.evaluate(OpKind.READ, "out/x")
    assert write.denied
    assert write.rule_id == "side_effects.ceiling.write"
    assert read.allowed


def test_validate_reports_unknown_side_effects(tmp_path: Path, capsys) -> None:
    skill = _write_skill(tmp_path, skill_yaml=_read_only_yaml(token="rocket-launch"))
    rc = main(["validate", str(skill), "--strictness", "local", "--output", "json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    errors = _side_effects_block(payload)["errors"]
    assert any("rocket-launch" in (error["summary"] or "") for error in errors)


def test_validate_passes_when_declaration_covers_permissions(tmp_path: Path, capsys) -> None:
    skill = _write_skill(
        tmp_path,
        skill_yaml=_read_only_yaml(),
        permissions=_CLOSED,
    )
    rc = main(["validate", str(skill), "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    notes = _side_effects_block(payload)["notes"]
    assert any("declared=read_only" in note and "implied=read_only" in note for note in notes)


def test_missing_side_effects_errors_when_matrix_cell_caps(tmp_path: Path, capsys) -> None:
    skill_yaml = (
        "name: review-notes\n"
        "strictness: team\n"
        "version: 1.0.0\n"
        "ownership:\n"
        "  team: platform\n"
        "risk:\n"
        "  level: high\n"
    )
    skill = _write_skill(tmp_path, skill_yaml=skill_yaml, permissions=_CLOSED)
    rc = main(["validate", str(skill), "--strictness", "team", "--output", "json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    errors = _side_effects_block(payload)["errors"]
    assert any("side_effects" in (error["summary"] or "") for error in errors)


def test_missing_permissions_notes_unverified(tmp_path: Path, capsys) -> None:
    skill_yaml = (
        "name: review-notes\n"
        "strictness: team\n"
        "version: 1.0.0\n"
        "ownership:\n"
        "  team: platform\n"
        "risk:\n"
        "  level: low\n"
        "  side_effects: read_only\n"
    )
    skill = _write_skill(tmp_path, skill_yaml=skill_yaml)
    rc = main(["validate", str(skill), "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    block = _side_effects_block(payload)
    text = " ".join(block["notes"]) + " ".join(
        (item.get("detail") or "") + (item.get("summary") or "") for item in block["warnings"]
    )
    assert "implied=unverified" in text
    assert "implied=destructive" not in text


def test_ceiling_keeps_permissions_rule_id_on_deny(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path,
        skill_yaml=_read_only_yaml(token="destructive"),
        permissions=_CLOSED,
    )
    decision = SideEffectCeiling.for_skill(skill, Strictness.LOCAL).evaluate(
        OpKind.WRITE, "out/x"
    )
    assert decision.denied
    assert decision.rule_id == "filesystem.write.empty-allowlist"


def test_ceiling_denies_all_without_permissions_at_org(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, skill_yaml=_read_only_yaml(token="destructive"))
    ceiling = SideEffectCeiling.for_skill(skill, Strictness.ORG)
    for kind, value in (
        (OpKind.READ, "a"),
        (OpKind.WRITE, "a"),
        (OpKind.ENV, "HOME"),
    ):
        decision = ceiling.evaluate(kind, value)
        assert decision.denied
        assert decision.rule_id == "side_effects.no-permissions"


def test_ceiling_denies_when_side_effects_omitted(tmp_path: Path) -> None:
    skill_yaml = (
        "name: review-notes\n"
        "strictness: local\n"
        "version: 1.0.0\n"
        "risk:\n"
        "  level: low\n"
    )
    skill = _write_skill(tmp_path, skill_yaml=skill_yaml, permissions=_WRITE_GRANT)
    decision = SideEffectCeiling.for_skill(skill, Strictness.LOCAL).evaluate(
        OpKind.WRITE, "out/x"
    )
    assert decision.denied
    assert decision.rule_id == "side_effects.undeclared"


def test_ceiling_denies_unbounded_write_when_permissions_file_is_absent(
    tmp_path: Path,
) -> None:
    skill = _write_skill(tmp_path, skill_yaml=_read_only_yaml())
    ceiling = SideEffectCeiling.for_skill(skill, Strictness.LOCAL)
    write = ceiling.evaluate(OpKind.WRITE, "/tmp/x")
    read = ceiling.evaluate(OpKind.READ, "/tmp/x")
    assert write.denied
    assert write.rule_id == "side_effects.ceiling.write"
    assert read.allowed


def test_ceiling_denies_namespace_pulled_from_the_command(tmp_path: Path) -> None:
    permissions = """\
schema_version: bulbasaur/v1
skill: review-notes
commands:
  default: deny
  allow:
    - pattern: '^kubectl'
network:
  default: deny
mcp_tools:
  default: deny
namespaces:
  deny: [kube-system]
filesystem:
  write_paths: []
"""
    skill = _write_skill(
        tmp_path,
        skill_yaml=_read_only_yaml(token="destructive"),
        permissions=permissions,
    )
    decision = SideEffectCeiling.for_skill(skill, Strictness.LOCAL).evaluate(
        OpKind.COMMAND, "kubectl get pods -n kube-system"
    )
    assert decision.denied
    assert decision.rule_id == "namespaces.deny.kube-system"


def test_permissions_hook_writes_ceiling_denied_audit(tmp_path: Path) -> None:
    from skillctl.permissions.hook import PermissionsHook

    skill = _write_skill(
        tmp_path,
        skill_yaml=_read_only_yaml(),
        permissions=_WRITE_GRANT,
    )
    sink = tmp_path / "audit.jsonl"
    hook = PermissionsHook.for_skill(skill, Strictness.LOCAL, audit_sink=sink)
    decision = hook.check(OpKind.WRITE, "out/x")
    assert decision.denied
    lines = sink.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "skill.side_effects.ceiling_denied"
    assert event["rule_id"] == "side_effects.ceiling.write"


def test_risk_check_op_reports_decision_and_exits_1(tmp_path: Path, capsys) -> None:
    skill = _write_skill(
        tmp_path,
        skill_yaml=_read_only_yaml(),
        permissions=_WRITE_GRANT,
    )
    rc = main(
        [
            "risk",
            "check",
            str(skill),
            "--op",
            "write:out/x",
            "--output",
            "json",
        ]
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decisions"][0]["rule_id"] == "side_effects.ceiling.write"
    assert payload["decisions"][0]["decision"] == "deny"

    bad = main(["risk", "check", str(skill), "--op", "nope"])
    assert bad == 2
