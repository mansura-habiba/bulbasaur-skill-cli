"""Tests for the policy module — loader, merger, engine, CLI."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from textwrap import dedent

import pytest

from skillctl.policy import (
    PolicyEngine,
    PolicyLoadError,
    load_policy,
    load_policy_from_dict,
    merge_policies,
)
from skillctl.policy.base import (
    ApproverRole,
    CheckOutcome,
    ForbiddenCommand,
    OwnershipRequirements,
    PermissionsRequirements,
    Policy,
    PolicyMetadata,
    RequiredArtifacts,
)
from skillctl.policy.catalog import list_catalog_names, resolve_catalog_path
from skillctl.strictness import Strictness


# ── helpers ────────────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content), encoding="utf-8")


def _scaffold_skill(skill_dir: Path) -> None:
    """Write a minimum skill scaffold (SKILL.md + skill.yaml)."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: t\ndescription: A test skill for policy tests.\n---\nbody",
        encoding="utf-8",
    )
    (skill_dir / "skill.yaml").write_text(
        "name: t\nstrictness: org\nversion: 1.0.0\n", encoding="utf-8"
    )


# ── catalog ────────────────────────────────────────────────────────────────


def test_catalog_lists_three_policies():
    names = list_catalog_names()
    assert "internal-tier-1" in names
    assert "hipaa-baseline" in names
    assert "soc2-type2-baseline" in names


def test_catalog_paths_resolve():
    for name in list_catalog_names():
        path = resolve_catalog_path(name)
        assert path is not None
        assert path.is_file()


def test_catalog_policies_load_cleanly():
    for name in list_catalog_names():
        path = resolve_catalog_path(name)
        policy = load_policy(path)
        assert policy.metadata.name == name
        assert policy.metadata.version


# ── loader ────────────────────────────────────────────────────────────────


def test_load_policy_rejects_missing_file(tmp_path):
    with pytest.raises(PolicyLoadError) as exc:
        load_policy(tmp_path / "nope.yaml")
    assert "not found" in exc.value.framework_error.summary


def test_load_policy_rejects_malformed_yaml(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("foo: [unbalanced\n", encoding="utf-8")
    with pytest.raises(PolicyLoadError):
        load_policy(p)


def test_load_policy_rejects_non_mapping(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("- list\n- not a mapping\n", encoding="utf-8")
    with pytest.raises(PolicyLoadError):
        load_policy(p)


def test_load_policy_rejects_missing_name(tmp_path):
    p = tmp_path / "bad.yaml"
    _write(p, """\
        policy:
          version: 1.0.0
    """)
    with pytest.raises(PolicyLoadError) as exc:
        load_policy(p)
    assert "name" in exc.value.framework_error.summary


def test_load_policy_rejects_missing_version(tmp_path):
    p = tmp_path / "bad.yaml"
    _write(p, """\
        policy:
          name: x
    """)
    with pytest.raises(PolicyLoadError):
        load_policy(p)


def test_load_policy_parses_full_schema(tmp_path):
    p = tmp_path / "full.yaml"
    _write(p, """\
        schema_version: bulbasaur/v1
        policy:
          name: full-test
          version: 2.0.0
          effective_date: 2026-01-01
          expiry_date: 2027-12-31
          authority: x@example.com
          description: A test policy.
          applies_to_strictness: [org, regulated]
          required_artifacts:
            files: [skill.yaml, permissions.yaml]
            directories: [evals/snapshots/]
            references_must_exist: true
          ownership:
            required_fields: [team, contact]
            last_reviewed_max_age_days: 180
            require_security_reviewer: true
          eval:
            min_score: 1.0
            min_threshold: 1.0
            required_suites: [behavior, injection]
            injection_corpus_pinned: true
            snapshots_required: true
            judge_must_be_llm: true
            model_upgrade:
              re_eval_required: true
              block_on_regression: true
              regression_threshold: 0.0
          permissions:
            require_default_deny: [commands, network]
            forbidden_commands:
              - pattern: '\\bdelete_all\\b'
                reason: destructive
            require_namespace_isolation: true
            redact_required_patterns: ['.*_TOKEN']
          audit:
            retention_days: 2555
            tamper_evident: true
            fail_mode: fail-closed
            required_fields: [model_version, prompt_hash]
          approval:
            required_approvers:
              - role: security
                count: 1
              - role: business-owner
                count: 1
            sign_off_yaml_required: true
          cost:
            max_tokens_per_run: 100000
            max_cost_usd_per_month: 1000.0
          compliance_frameworks:
            - id: HIPAA
              controls: ['164.308', '164.312']
          custom_validators: [pii_scanner]
    """)
    policy = load_policy(p)
    assert policy.metadata.name == "full-test"
    assert policy.metadata.version == "2.0.0"
    assert policy.applies_to_strictness == ("org", "regulated")
    assert policy.required_artifacts.files == ("skill.yaml", "permissions.yaml")
    assert policy.ownership.last_reviewed_max_age_days == 180
    assert policy.eval.judge_must_be_llm is True
    assert policy.eval.model_upgrade.block_on_regression is True
    assert policy.permissions.forbidden_commands[0].pattern == r"\bdelete_all\b"
    assert policy.audit.fail_mode == "fail-closed"
    assert policy.approval.required_approvers[0].role == "security"
    assert policy.cost.max_tokens_per_run == 100000
    assert policy.compliance_frameworks[0].id == "HIPAA"


# ── PolicyMetadata.is_active ──────────────────────────────────────────────


def test_metadata_is_active_inside_window():
    m = PolicyMetadata(
        name="x",
        version="1",
        effective_date=date(2020, 1, 1),
        expiry_date=date(2099, 1, 1),
    )
    assert m.is_active(today=date(2026, 6, 1))


def test_metadata_is_inactive_before_window():
    m = PolicyMetadata(
        name="x", version="1", effective_date=date(2099, 1, 1)
    )
    assert not m.is_active(today=date(2026, 6, 1))


def test_metadata_is_inactive_after_expiry():
    m = PolicyMetadata(
        name="x", version="1", expiry_date=date(2020, 1, 1)
    )
    assert not m.is_active(today=date(2026, 6, 1))


# ── merger ────────────────────────────────────────────────────────────────


def _policy_with(**kwargs) -> Policy:
    return Policy(metadata=PolicyMetadata(name="x", version="1.0.0"), **kwargs)


def test_merge_empty_returns_default():
    result = merge_policies()
    assert result.metadata.name == "empty"


def test_merge_one_returns_unchanged():
    p = _policy_with()
    assert merge_policies(p) is p


def test_merge_unions_required_artifacts():
    a = _policy_with(
        required_artifacts=RequiredArtifacts(files=("a.yaml", "b.yaml"))
    )
    b = _policy_with(
        required_artifacts=RequiredArtifacts(files=("b.yaml", "c.yaml"))
    )
    merged = merge_policies(a, b)
    assert merged.required_artifacts.files == ("a.yaml", "b.yaml", "c.yaml")


def test_merge_tightest_last_reviewed_wins():
    a = _policy_with(ownership=OwnershipRequirements(last_reviewed_max_age_days=365))
    b = _policy_with(ownership=OwnershipRequirements(last_reviewed_max_age_days=90))
    merged = merge_policies(a, b)
    assert merged.ownership.last_reviewed_max_age_days == 90


def test_merge_unions_forbidden_commands_dedupe_by_pattern():
    a = _policy_with(
        permissions=PermissionsRequirements(
            forbidden_commands=(ForbiddenCommand(pattern=r"\brm\b"),)
        )
    )
    b = _policy_with(
        permissions=PermissionsRequirements(
            forbidden_commands=(
                ForbiddenCommand(pattern=r"\brm\b"),
                ForbiddenCommand(pattern=r"\bdrop\b"),
            )
        )
    )
    merged = merge_policies(a, b)
    patterns = [f.pattern for f in merged.permissions.forbidden_commands]
    assert patterns == [r"\brm\b", r"\bdrop\b"]


def test_merge_strictest_fail_mode_wins():
    from skillctl.policy.base import AuditRequirements

    a = _policy_with(audit=AuditRequirements(fail_mode="fail-open"))
    b = _policy_with(audit=AuditRequirements(fail_mode="fail-closed"))
    c = _policy_with(audit=AuditRequirements(fail_mode="fail-degraded"))
    merged = merge_policies(a, b, c)
    assert merged.audit.fail_mode == "fail-closed"


def test_merge_max_approver_count_per_role():
    a = _policy_with(
        approval=__import__(
            "skillctl.policy.base", fromlist=["ApprovalRequirements"]
        ).ApprovalRequirements(
            required_approvers=(ApproverRole(role="sec", count=1),)
        )
    )
    b = _policy_with(
        approval=__import__(
            "skillctl.policy.base", fromlist=["ApprovalRequirements"]
        ).ApprovalRequirements(
            required_approvers=(ApproverRole(role="sec", count=2),)
        )
    )
    merged = merge_policies(a, b)
    assert merged.approval.required_approvers[0].count == 2


# ── PolicyEngine ──────────────────────────────────────────────────────────


def test_engine_skip_when_strictness_does_not_match(tmp_path):
    _scaffold_skill(tmp_path)
    policy = _policy_with(applies_to_strictness=("regulated",))
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    assert any(c.outcome == CheckOutcome.SKIP for c in result.checks)


def test_engine_fail_when_policy_outside_window(tmp_path):
    _scaffold_skill(tmp_path)
    policy = Policy(
        metadata=PolicyMetadata(
            name="expired", version="1", expiry_date=date(2020, 1, 1)
        )
    )
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    assert not result.passed
    assert any("effective window" in c.requirement for c in result.checks)


def test_engine_fail_on_missing_required_file(tmp_path):
    _scaffold_skill(tmp_path)
    policy = _policy_with(
        required_artifacts=RequiredArtifacts(files=("missing.yaml",))
    )
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    assert not result.passed
    fails = [c.requirement for c in result.failures]
    assert any("missing.yaml" in r for r in fails)


def test_engine_pass_when_required_files_present(tmp_path):
    _scaffold_skill(tmp_path)
    policy = _policy_with(
        required_artifacts=RequiredArtifacts(files=("skill.yaml",))
    )
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    assert result.passed


def test_engine_ownership_last_reviewed_fail_on_stale(tmp_path):
    _scaffold_skill(tmp_path)
    (tmp_path / "ownership.yaml").write_text(
        f"team: x\ncontact: x@y\nlast_reviewed: {date(2020, 1, 1).isoformat()}\n",
        encoding="utf-8",
    )
    policy = _policy_with(
        ownership=OwnershipRequirements(last_reviewed_max_age_days=180)
    )
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    fails = [c.requirement for c in result.failures]
    assert any("within 180 days" in r for r in fails)


def test_engine_ownership_last_reviewed_pass_on_fresh(tmp_path):
    _scaffold_skill(tmp_path)
    today = date.today().isoformat()
    (tmp_path / "ownership.yaml").write_text(
        f"team: x\ncontact: x@y\nlast_reviewed: {today}\n", encoding="utf-8"
    )
    policy = _policy_with(
        ownership=OwnershipRequirements(last_reviewed_max_age_days=365)
    )
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    passes = [c.requirement for c in result.checks if c.outcome == CheckOutcome.PASS]
    assert any("within 365 days" in r for r in passes)


def test_engine_eval_required_suites(tmp_path):
    _scaffold_skill(tmp_path)
    evals = tmp_path / "evals"
    evals.mkdir()
    (evals / "behavior.json").write_text(
        json.dumps({"skill_name": "t", "evals": [{"id": 1, "prompt": "p"}]}),
        encoding="utf-8",
    )
    from skillctl.policy.base import EvalRequirements

    policy = _policy_with(
        eval=EvalRequirements(required_suites=("behavior", "injection"))
    )
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    requirements = [(c.requirement, c.outcome) for c in result.checks]
    assert ("suite `behavior` present with ≥1 case", CheckOutcome.PASS) in requirements
    assert ("suite `injection` present", CheckOutcome.FAIL) in requirements


def test_engine_permissions_default_deny_check(tmp_path):
    _scaffold_skill(tmp_path)
    (tmp_path / "permissions.yaml").write_text(
        dedent("""\
            schema_version: bulbasaur/v1
            skill: t
            commands:
              default: allow
        """),
        encoding="utf-8",
    )
    policy = _policy_with(
        permissions=PermissionsRequirements(
            require_default_deny=("commands",)
        )
    )
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    fails = [c.requirement for c in result.failures]
    assert any("commands.default = deny" in r for r in fails)


def test_engine_cost_check_returns_unknown(tmp_path):
    _scaffold_skill(tmp_path)
    from skillctl.policy.base import CostRequirements

    policy = _policy_with(cost=CostRequirements(max_tokens_per_run=10000))
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    assert any(
        c.outcome == CheckOutcome.UNKNOWN and "tokens" in c.requirement
        for c in result.checks
    )


# ── catalog policies actually validate ────────────────────────────────────


def test_internal_tier_1_validates_against_minimal_skill(tmp_path):
    """The internal-tier-1 policy is the lightest of the three; a minimal but
    well-formed skill should produce predictable check counts."""
    _scaffold_skill(tmp_path)
    path = resolve_catalog_path("internal-tier-1")
    policy = load_policy(path)
    result = PolicyEngine(policy).validate(tmp_path, Strictness.ORG)
    # Some checks pass (skill.yaml present), some fail (no permissions.yaml,
    # no behavior.json, etc.).
    assert result.total_checks > 5
    assert not result.passed  # missing permissions.yaml + ownership.yaml + behavior.json


# ── PolicyValidator integration ───────────────────────────────────────────


def test_policy_validator_fails_when_no_policies_at_org(tmp_path):
    """At org strictness, the validator must error if no policies declared."""
    from skillctl.validate.policy_validator import PolicyValidator

    _scaffold_skill(tmp_path)
    result = PolicyValidator().run(tmp_path, Strictness.ORG)
    assert not result.passed
    assert any("no policies declared" in e.summary for e in result.errors)


def test_policy_validator_passes_at_local_with_no_policies(tmp_path):
    """At local strictness, no policies is fine."""
    from skillctl.validate.policy_validator import PolicyValidator

    _scaffold_skill(tmp_path)
    result = PolicyValidator().run(tmp_path, Strictness.LOCAL)
    assert result.passed


def test_policy_validator_resolves_catalog_short_name(tmp_path):
    """A skill declaring `policies: [internal-tier-1]` resolves from the catalog."""
    from skillctl.validate.policy_validator import PolicyValidator

    _scaffold_skill(tmp_path)
    (tmp_path / "skill.yaml").write_text(
        dedent("""\
            name: t
            strictness: org
            version: 1.0.0
            policies:
              - internal-tier-1
        """),
        encoding="utf-8",
    )
    result = PolicyValidator().run(tmp_path, Strictness.ORG)
    # The skill is minimal — policy will surface failures, but the validator
    # successfully resolved + ran the policy.
    assert any("policy `internal-tier-1`" in note for note in result.notes)


def test_policy_validator_unresolvable_policy_is_error(tmp_path):
    from skillctl.validate.policy_validator import PolicyValidator

    _scaffold_skill(tmp_path)
    (tmp_path / "skill.yaml").write_text(
        dedent("""\
            name: t
            strictness: org
            version: 1.0.0
            policies:
              - does-not-exist
        """),
        encoding="utf-8",
    )
    result = PolicyValidator().run(tmp_path, Strictness.ORG)
    assert any("cannot resolve" in e.summary for e in result.errors)


def test_skill_yaml_round_trip_preserves_policies(tmp_path):
    from skillctl.skill_yaml import (
        SkillOverlay,
        load_skill_yaml,
        write_skill_yaml,
    )

    overlay = SkillOverlay(
        name="t",
        strictness=Strictness.ORG,
        version="1.0.0",
        policies=["internal-tier-1", "./policies/local.yaml"],
    )
    p = tmp_path / "skill.yaml"
    write_skill_yaml(p, overlay)
    loaded = load_skill_yaml(tmp_path)
    assert loaded.policies == ["internal-tier-1", "./policies/local.yaml"]
