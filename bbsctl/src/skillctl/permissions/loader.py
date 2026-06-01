"""Load and merge `permissions.yaml`.

Layered resolution (deepest first):

  1. Org default — passed in as the `org_default` argument; usually loaded from
     `~/.config/bbsctl/org-permissions.yaml` or `$BBSCTL_ORG_PERMISSIONS`.
  2. Skill override — the `permissions.yaml` next to `SKILL.md`.

Merge semantics: **deny wins**.

  - Allow rules from both layers are unioned.
  - Deny rules from both layers are unioned.
  - Defaults: a deny default in either layer becomes the merged default.

The validator (separate module) enforces that a skill's allow rule must not
widen what the org default permits. The merger does not refuse merges on
widening; the validator surfaces them as errors.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError

from .base import DecisionType, Permissions, Rule, RuleGroup

_PERMISSIONS_YAML_NAME = "permissions.yaml"


class PermissionsLoadError(Exception):
    """Raised when permissions.yaml is unparseable or malformed.

    Carries a FrameworkError for the caller to emit.
    """

    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


def load_permissions(skill_dir: Path) -> Permissions | None:
    """Load `permissions.yaml` from `skill_dir`.

    Returns None if the file is absent — callers decide whether that is an
    error per the strictness rung. Raises PermissionsLoadError on malformed
    YAML or schema violations.
    """
    path = skill_dir / _PERMISSIONS_YAML_NAME
    if not path.exists():
        return None

    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path)
    except Exception as exc:
        raise PermissionsLoadError(
            FrameworkError(
                summary="permissions.yaml: YAML parse error",
                detail=str(exc),
                fix=(
                    "Fix the YAML syntax. See docs/permissions.md for the schema."
                ),
                docs="../docs/permissions.md",
            )
        ) from exc

    if not isinstance(raw, dict):
        raise PermissionsLoadError(
            FrameworkError(
                summary="permissions.yaml: top-level must be a mapping",
                fix="Start with `schema_version: bulbasaur/v1` and `skill: <name>`.",
            )
        )

    return _parse(raw, path=path)


def merge_permissions(
    *, org_default: Permissions | None, skill: Permissions | None
) -> Permissions | None:
    """Merge org_default and skill permissions. Deny-wins.

    If both are None, returns None. If one is None, returns the other.
    """
    if org_default is None and skill is None:
        return None
    if org_default is None:
        return skill
    if skill is None:
        return org_default

    merged_defaults: dict[RuleGroup, DecisionType] = {}
    for group in RuleGroup:
        org_d = org_default.defaults.get(group)
        skl_d = skill.defaults.get(group)
        if DecisionType.DENY in {org_d, skl_d}:
            merged_defaults[group] = DecisionType.DENY
        elif DecisionType.ALLOW in {org_d, skl_d}:
            merged_defaults[group] = DecisionType.ALLOW

    return Permissions(
        skill=skill.skill or org_default.skill,
        schema_version=skill.schema_version,
        defaults=merged_defaults,
        commands_allow=list(org_default.commands_allow) + list(skill.commands_allow),
        commands_deny=list(org_default.commands_deny) + list(skill.commands_deny),
        namespaces_allow=_unique(org_default.namespaces_allow + skill.namespaces_allow),
        namespaces_deny=_unique(org_default.namespaces_deny + skill.namespaces_deny),
        network_allow=list(org_default.network_allow) + list(skill.network_allow),
        network_deny=list(org_default.network_deny) + list(skill.network_deny),
        filesystem_read_paths=_unique(
            org_default.filesystem_read_paths + skill.filesystem_read_paths
        ),
        filesystem_write_paths=_unique(
            org_default.filesystem_write_paths + skill.filesystem_write_paths
        ),
        env_allow=_unique(org_default.env_allow + skill.env_allow),
        env_redact=_unique(org_default.env_redact + skill.env_redact),
        mcp_tools_allow=list(org_default.mcp_tools_allow) + list(skill.mcp_tools_allow),
        mcp_tools_deny=list(org_default.mcp_tools_deny) + list(skill.mcp_tools_deny),
    )


def _unique(items: list[str]) -> list[str]:
    """Preserve order; drop duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _parse(raw: dict[str, Any], *, path: Path) -> Permissions:
    """Parse a raw permissions.yaml dict into Permissions.

    Tolerates missing groups; aggressive on regex syntax errors and on
    malformed rule shapes (a list when a dict is expected, etc.).
    """
    skill = str(raw.get("skill") or "")
    schema_version = str(raw.get("schema_version") or "bulbasaur/v1")

    defaults: dict[RuleGroup, DecisionType] = {}

    commands_allow: list[Rule] = []
    commands_deny: list[Rule] = []
    if (cmds := raw.get("commands")) and isinstance(cmds, dict):
        defaults[RuleGroup.COMMANDS] = _parse_default(cmds, group=RuleGroup.COMMANDS, path=path)
        commands_allow = _parse_rule_list(
            cmds.get("allow"), group=RuleGroup.COMMANDS, decision=DecisionType.ALLOW, path=path
        )
        commands_deny = _parse_rule_list(
            cmds.get("deny"), group=RuleGroup.COMMANDS, decision=DecisionType.DENY, path=path
        )

    namespaces_allow: list[str] = []
    namespaces_deny: list[str] = []
    if (ns := raw.get("namespaces")) and isinstance(ns, dict):
        namespaces_allow = _parse_string_list(ns.get("allow"))
        namespaces_deny = _parse_string_list(ns.get("deny"))

    network_allow: list[Rule] = []
    network_deny: list[Rule] = []
    if (net := raw.get("network")) and isinstance(net, dict):
        defaults[RuleGroup.NETWORK] = _parse_default(net, group=RuleGroup.NETWORK, path=path)
        network_allow = _parse_rule_list(
            net.get("allowed_sites"),
            group=RuleGroup.NETWORK,
            decision=DecisionType.ALLOW,
            path=path,
        )
        network_deny = _parse_rule_list(
            net.get("denied_sites"),
            group=RuleGroup.NETWORK,
            decision=DecisionType.DENY,
            path=path,
        )

    filesystem_read_paths: list[str] = []
    filesystem_write_paths: list[str] = []
    if (fs := raw.get("filesystem")) and isinstance(fs, dict):
        filesystem_read_paths = _parse_string_list(fs.get("read_paths"))
        filesystem_write_paths = _parse_string_list(fs.get("write_paths"))

    env_allow: list[str] = []
    env_redact: list[str] = []
    if (env := raw.get("env")) and isinstance(env, dict):
        env_allow = _parse_string_list(env.get("allow"))
        env_redact = _parse_string_list(env.get("redact"))

    mcp_allow: list[Rule] = []
    mcp_deny: list[Rule] = []
    if (mcp := raw.get("mcp_tools")) and isinstance(mcp, dict):
        defaults[RuleGroup.MCP_TOOLS] = _parse_default(mcp, group=RuleGroup.MCP_TOOLS, path=path)
        mcp_allow = _parse_glob_list(
            mcp.get("allow"), group=RuleGroup.MCP_TOOLS, decision=DecisionType.ALLOW, path=path
        )
        mcp_deny = _parse_glob_list(
            mcp.get("deny"), group=RuleGroup.MCP_TOOLS, decision=DecisionType.DENY, path=path
        )

    return Permissions(
        skill=skill,
        schema_version=schema_version,
        defaults=defaults,
        commands_allow=commands_allow,
        commands_deny=commands_deny,
        namespaces_allow=namespaces_allow,
        namespaces_deny=namespaces_deny,
        network_allow=network_allow,
        network_deny=network_deny,
        filesystem_read_paths=filesystem_read_paths,
        filesystem_write_paths=filesystem_write_paths,
        env_allow=env_allow,
        env_redact=env_redact,
        mcp_tools_allow=mcp_allow,
        mcp_tools_deny=mcp_deny,
    )


def _parse_default(group_dict: dict, *, group: RuleGroup, path: Path) -> DecisionType:
    raw = group_dict.get("default")
    if raw is None:
        # No explicit default; return ALLOW as a benign placeholder.
        # The merger / validator decide based on strictness.
        return DecisionType.ALLOW
    try:
        return DecisionType(str(raw).lower())
    except ValueError as exc:
        raise PermissionsLoadError(
            FrameworkError(
                summary=(
                    f"permissions.yaml: invalid `{group.value}.default` "
                    f"value: {raw!r}"
                ),
                detail=f"path: {path}",
                fix="`default` must be either `allow` or `deny`.",
            )
        ) from exc


def _parse_string_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        return [raw]
    return []


def _parse_rule_list(
    raw: Any, *, group: RuleGroup, decision: DecisionType, path: Path
) -> list[Rule]:
    """Parse a list of {pattern, reason} dicts into Rules.

    Validates regex syntax at parse time so runtime cannot crash on a bad
    pattern. Each pattern compiles once.
    """
    if not raw:
        return []
    if not isinstance(raw, list):
        raise PermissionsLoadError(
            FrameworkError(
                summary=(
                    f"permissions.yaml: `{group.value}.{decision.value}` must be a list"
                ),
                detail=f"path: {path}",
                fix=(
                    "Each entry is a mapping with `pattern` (regex) and optional `reason`."
                ),
            )
        )

    rules: list[Rule] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise PermissionsLoadError(
                FrameworkError(
                    summary=(
                        f"permissions.yaml: `{group.value}.{decision.value}[{i}]` "
                        "must be a mapping"
                    ),
                    detail=f"path: {path}; got: {type(entry).__name__}",
                    fix="Each entry is `{pattern: ..., reason: ...}`.",
                )
            )
        pattern = entry.get("pattern")
        if not pattern or not isinstance(pattern, str):
            raise PermissionsLoadError(
                FrameworkError(
                    summary=(
                        f"permissions.yaml: `{group.value}.{decision.value}[{i}]` "
                        "missing required `pattern`"
                    ),
                    detail=f"path: {path}",
                    fix="Add a non-empty `pattern:` (regex string).",
                )
            )
        try:
            re.compile(pattern)
        except re.error as exc:
            raise PermissionsLoadError(
                FrameworkError(
                    summary=(
                        f"permissions.yaml: invalid regex in "
                        f"`{group.value}.{decision.value}[{i}].pattern`"
                    ),
                    detail=f"pattern: {pattern!r}; error: {exc}",
                    fix="Fix the regex syntax. Test it with `python -c \"import re; re.compile(...)\".",
                )
            ) from exc

        reason = str(entry.get("reason") or "")
        rule_id = str(entry.get("id") or "")
        rules.append(
            Rule(group=group, decision=decision, pattern=pattern, reason=reason, id=rule_id)
        )
    return rules


def _parse_glob_list(
    raw: Any, *, group: RuleGroup, decision: DecisionType, path: Path
) -> list[Rule]:
    """Parse mcp_tools allow/deny — accepts simple glob strings or dicts.

    `["policy-mcp.*"]` and `[{pattern: "policy-mcp.*", reason: "..."}]` are
    both accepted. Globs are converted to anchored regex (`.` is literal,
    `*` becomes `.*`).
    """
    if not raw:
        return []
    if not isinstance(raw, list):
        raise PermissionsLoadError(
            FrameworkError(
                summary=(
                    f"permissions.yaml: `{group.value}.{decision.value}` must be a list"
                ),
                detail=f"path: {path}",
                fix="Use a list of glob strings or {pattern, reason} mappings.",
            )
        )

    rules: list[Rule] = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            glob = entry
            reason = ""
            rule_id = ""
        elif isinstance(entry, dict):
            glob = entry.get("pattern", "")
            if not glob:
                raise PermissionsLoadError(
                    FrameworkError(
                        summary=(
                            f"permissions.yaml: `{group.value}.{decision.value}[{i}]` "
                            "missing `pattern`"
                        ),
                        fix="Add `pattern:` with a glob like `policy-mcp.*`.",
                    )
                )
            reason = str(entry.get("reason") or "")
            rule_id = str(entry.get("id") or "")
        else:
            raise PermissionsLoadError(
                FrameworkError(
                    summary=(
                        f"permissions.yaml: `{group.value}.{decision.value}[{i}]` "
                        "must be a string or mapping"
                    ),
                    detail=f"path: {path}",
                    fix="Use a glob string or `{pattern, reason}` mapping.",
                )
            )
        regex = _glob_to_regex(glob)
        rules.append(
            Rule(
                group=group,
                decision=decision,
                pattern=regex,
                reason=reason,
                id=rule_id,
            )
        )
    return rules


def _glob_to_regex(glob: str) -> str:
    """Convert a simple glob to an anchored regex.

    Rules:
      * → .*
      ? → .
      . → \\.  (literal)
      everything else literal
    """
    out: list[str] = ["^"]
    for ch in glob:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        elif ch in r".+()[]{}|\^$":
            out.append("\\" + ch)
        else:
            out.append(ch)
    out.append("$")
    return "".join(out)


__all__ = ["PermissionsLoadError", "load_permissions", "merge_permissions"]
