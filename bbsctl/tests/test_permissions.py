"""Tests for the permissions module — loader, merger, and Guardrails engine."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from skillctl.permissions import (
    DecisionType,
    Guardrails,
    Permissions,
    Rule,
    RuleGroup,
)
from skillctl.permissions.loader import (
    PermissionsLoadError,
    load_permissions,
    merge_permissions,
)


# ── helpers ────────────────────────────────────────────────────────────────


def _write_permissions(skill_dir: Path, content: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "permissions.yaml").write_text(dedent(content), encoding="utf-8")


# ── loader ─────────────────────────────────────────────────────────────────


def test_load_returns_none_when_file_absent(tmp_path):
    assert load_permissions(tmp_path) is None


def test_load_rejects_malformed_yaml(tmp_path):
    (tmp_path / "permissions.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
    with pytest.raises(PermissionsLoadError) as exc:
        load_permissions(tmp_path)
    assert "YAML parse error" in exc.value.framework_error.summary


def test_load_rejects_non_mapping_top_level(tmp_path):
    (tmp_path / "permissions.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(PermissionsLoadError) as exc:
        load_permissions(tmp_path)
    assert "must be a mapping" in exc.value.framework_error.summary


def test_load_parses_full_schema(tmp_path):
    _write_permissions(tmp_path, """\
        schema_version: bulbasaur/v1
        skill: mq-executor
        commands:
          default: deny
          allow:
            - pattern: '^oc get'
              reason: read-only
          deny:
            - pattern: '\\boc delete\\b'
              reason: destructive
        namespaces:
          allow: [mq-prod, mq-staging]
          deny: [kube-system, flux-system]
        network:
          default: deny
          allowed_sites:
            - pattern: '^https://docs\\.openshift\\.com/'
          denied_sites:
            - pattern: '^http://'
        filesystem:
          read_paths:
            - "/var/log/openshift/**"
          write_paths: []
        env:
          allow: [KUBECONFIG, OC_CONTEXT]
          redact: ['.*_TOKEN', '.*_SECRET']
        mcp_tools:
          default: deny
          allow:
            - policy-mcp.check_namespace_excluded
            - kubectl-mcp.execute_action
          deny:
            - "*.delete_*"
    """)
    p = load_permissions(tmp_path)

    assert p is not None
    assert p.skill == "mq-executor"
    assert p.default_for(RuleGroup.COMMANDS) == DecisionType.DENY
    assert len(p.commands_allow) == 1
    assert p.commands_allow[0].reason == "read-only"
    assert len(p.commands_deny) == 1
    assert p.namespaces_allow == ["mq-prod", "mq-staging"]
    assert p.namespaces_deny == ["kube-system", "flux-system"]
    assert p.default_for(RuleGroup.NETWORK) == DecisionType.DENY
    assert len(p.network_allow) == 1
    assert p.filesystem_read_paths == ["/var/log/openshift/**"]
    assert p.env_allow == ["KUBECONFIG", "OC_CONTEXT"]
    assert p.env_redact == [".*_TOKEN", ".*_SECRET"]
    assert p.default_for(RuleGroup.MCP_TOOLS) == DecisionType.DENY
    assert len(p.mcp_tools_allow) == 2
    assert len(p.mcp_tools_deny) == 1


def test_load_rejects_invalid_regex(tmp_path):
    _write_permissions(tmp_path, """\
        skill: bad
        commands:
          allow:
            - pattern: '[bad'  # unbalanced bracket
    """)
    with pytest.raises(PermissionsLoadError) as exc:
        load_permissions(tmp_path)
    assert "invalid regex" in exc.value.framework_error.summary


def test_load_rejects_invalid_default_value(tmp_path):
    _write_permissions(tmp_path, """\
        skill: bad
        commands:
          default: maybe
    """)
    with pytest.raises(PermissionsLoadError):
        load_permissions(tmp_path)


def test_load_rejects_rule_missing_pattern(tmp_path):
    _write_permissions(tmp_path, """\
        skill: bad
        commands:
          allow:
            - reason: missing pattern
    """)
    with pytest.raises(PermissionsLoadError) as exc:
        load_permissions(tmp_path)
    assert "missing required `pattern`" in exc.value.framework_error.summary


def test_load_accepts_mcp_tools_as_glob_strings(tmp_path):
    """mcp_tools allow accepts bare strings as globs, not just dicts."""
    _write_permissions(tmp_path, """\
        skill: ok
        mcp_tools:
          allow:
            - policy-mcp.check_namespace_excluded
    """)
    p = load_permissions(tmp_path)
    assert len(p.mcp_tools_allow) == 1
    # glob → anchored regex; verify the regex matches what we expect
    r = p.mcp_tools_allow[0]
    assert r.pattern.startswith("^")
    assert r.pattern.endswith("$")


# ── merge ───────────────────────────────────────────────────────────────────


def test_merge_with_both_none_returns_none():
    assert merge_permissions(org_default=None, skill=None) is None


def test_merge_with_one_none_returns_other():
    p = Permissions(skill="x")
    assert merge_permissions(org_default=p, skill=None) is p
    assert merge_permissions(org_default=None, skill=p) is p


def test_merge_deny_wins_on_defaults():
    org = Permissions(skill="org", defaults={RuleGroup.COMMANDS: DecisionType.ALLOW})
    skl = Permissions(skill="skl", defaults={RuleGroup.COMMANDS: DecisionType.DENY})
    merged = merge_permissions(org_default=org, skill=skl)
    assert merged.default_for(RuleGroup.COMMANDS) == DecisionType.DENY


def test_merge_unions_allow_and_deny_rules():
    org = Permissions(
        skill="org",
        commands_deny=[Rule(RuleGroup.COMMANDS, DecisionType.DENY, r"\brm -rf\b")],
        namespaces_deny=["kube-system"],
    )
    skl = Permissions(
        skill="skl",
        commands_deny=[Rule(RuleGroup.COMMANDS, DecisionType.DENY, r"\bsudo\b")],
        namespaces_deny=["flux-system", "kube-system"],
    )
    merged = merge_permissions(org_default=org, skill=skl)
    assert len(merged.commands_deny) == 2
    # de-duped
    assert merged.namespaces_deny == ["kube-system", "flux-system"]


# ── Guardrails — commands ──────────────────────────────────────────────────


def _make_guardrails(**kwargs) -> Guardrails:
    return Guardrails(Permissions(**kwargs))


def test_command_deny_short_circuits_before_allow():
    g = _make_guardrails(
        commands_allow=[
            Rule(RuleGroup.COMMANDS, DecisionType.ALLOW, r"^kubectl"),
        ],
        commands_deny=[
            Rule(RuleGroup.COMMANDS, DecisionType.DENY, r"\bkubectl exec\b.*-it"),
        ],
    )
    d = g.evaluate_command("kubectl exec pod -it -- /bin/bash")
    assert d.denied


def test_command_allow_returns_allow_decision():
    g = _make_guardrails(
        commands_allow=[Rule(RuleGroup.COMMANDS, DecisionType.ALLOW, r"^oc get")],
    )
    d = g.evaluate_command("oc get pods")
    assert d.allowed
    assert d.rule_id.startswith("commands.allow.")


def test_command_no_match_falls_back_to_default():
    g = _make_guardrails(defaults={RuleGroup.COMMANDS: DecisionType.DENY})
    d = g.evaluate_command("oc get pods")
    assert d.denied
    assert d.rule_id == "default.commands"


def test_command_namespace_deny_overrides_allow():
    g = _make_guardrails(
        commands_allow=[
            Rule(RuleGroup.COMMANDS, DecisionType.ALLOW, r"^kubectl rollout"),
        ],
        namespaces_deny=["kube-system"],
    )
    d = g.evaluate_command(
        "kubectl rollout restart deploy/foo -n kube-system",
        namespace="kube-system",
    )
    assert d.denied
    assert "kube-system" in d.rule_id


def test_command_namespace_allow_required_when_set():
    """Allow-list is exclusive: namespaces not in it are denied."""
    g = _make_guardrails(namespaces_allow=["mq-prod", "mq-staging"])
    d = g.evaluate_command("kubectl get pods -n default", namespace="default")
    assert d.denied


def test_command_no_namespace_rules_passes():
    g = _make_guardrails(
        commands_allow=[Rule(RuleGroup.COMMANDS, DecisionType.ALLOW, r"^kubectl get")],
    )
    d = g.evaluate_command("kubectl get pods")
    assert d.allowed


def test_extract_namespace_from_command():
    assert Guardrails.extract_namespace("kubectl get pods -n mq-prod") == "mq-prod"
    assert (
        Guardrails.extract_namespace("kubectl get pods --namespace mq-staging")
        == "mq-staging"
    )
    assert Guardrails.extract_namespace("kubectl get pods") is None


# ── Guardrails — network ───────────────────────────────────────────────────


def test_network_deny_wins():
    g = _make_guardrails(
        network_allow=[Rule(RuleGroup.NETWORK, DecisionType.ALLOW, r"^https://")],
        network_deny=[Rule(RuleGroup.NETWORK, DecisionType.DENY, r"\.internal/")],
    )
    d = g.evaluate_url("https://example.internal/")
    assert d.denied


def test_network_no_match_default_deny():
    g = _make_guardrails(defaults={RuleGroup.NETWORK: DecisionType.DENY})
    d = g.evaluate_url("https://example.com/")
    assert d.denied
    assert d.rule_id == "default.network"


# ── Guardrails — filesystem ────────────────────────────────────────────────


def test_filesystem_allow_via_glob():
    g = _make_guardrails(filesystem_read_paths=["/var/log/openshift/**"])
    assert g.evaluate_read("/var/log/openshift/audit.log").allowed
    assert g.evaluate_read("/etc/passwd").denied


def test_filesystem_no_rules_means_allow():
    g = _make_guardrails()
    assert g.evaluate_read("/anything").allowed
    assert g.evaluate_write("/anywhere").allowed


def test_filesystem_write_paths_empty_when_allow_list_present_blocks_all():
    g = _make_guardrails(
        filesystem_read_paths=["/data/**"],
        filesystem_write_paths=["/data/output/**"],
    )
    assert g.evaluate_write("/data/input/file").denied
    assert g.evaluate_write("/data/output/file").allowed


# ── Guardrails — env ───────────────────────────────────────────────────────


def test_env_allow_list_is_exclusive():
    g = _make_guardrails(env_allow=["KUBECONFIG", "OC_CONTEXT"])
    assert g.evaluate_env("KUBECONFIG").allowed
    assert g.evaluate_env("AWS_SECRET_ACCESS_KEY").denied


def test_env_no_allow_list_means_open():
    g = _make_guardrails()
    assert g.evaluate_env("ANYTHING").allowed


def test_env_redaction_pattern_matches():
    g = _make_guardrails(env_redact=[r".*_TOKEN", r".*_SECRET"])
    assert g.should_redact("GITHUB_TOKEN")
    assert g.should_redact("AWS_SECRET_ACCESS_KEY")
    assert not g.should_redact("KUBECONFIG")


# ── Guardrails — mcp tools ─────────────────────────────────────────────────


def test_mcp_tool_glob_matching():
    # Using the loader-produced glob → regex form.
    from skillctl.permissions.loader import _glob_to_regex

    g = _make_guardrails(
        mcp_tools_allow=[
            Rule(RuleGroup.MCP_TOOLS, DecisionType.ALLOW, _glob_to_regex("policy-mcp.*"))
        ],
        mcp_tools_deny=[
            Rule(RuleGroup.MCP_TOOLS, DecisionType.DENY, _glob_to_regex("*.delete_*"))
        ],
    )
    assert g.evaluate_mcp_tool("policy-mcp.check_namespace_excluded").allowed
    assert g.evaluate_mcp_tool("kubectl-mcp.delete_pod").denied


def test_mcp_tool_default_deny():
    g = _make_guardrails(defaults={RuleGroup.MCP_TOOLS: DecisionType.DENY})
    d = g.evaluate_mcp_tool("anything.do_thing")
    assert d.denied
    assert d.rule_id == "default.mcp_tools"
