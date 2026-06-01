"""Permissions data model.

The schema mirrors `docs/permissions.md`. Six top-level groups:

  commands      anchored regex over shell command lines
  namespaces    kubernetes namespace allow/deny for write actions
  network       URL patterns for references + runtime fetches
  filesystem    POSIX glob over read/write paths
  env           env var allow + redact patterns
  mcp_tools     glob over <server>.<tool> names

Each group has an optional `default` (allow | deny) and `allow` / `deny` lists.
Each rule carries an `id` so audit JSONL can reference it deterministically.
The id is auto-generated from the group + pattern hash if not supplied.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class DecisionType(str, Enum):
    """Possible outcomes of evaluating an op against the rules."""

    ALLOW = "allow"
    DENY = "deny"


class RuleGroup(str, Enum):
    """The six rule groups, used as namespace prefixes for rule ids."""

    COMMANDS = "commands"
    NAMESPACES = "namespaces"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    ENV = "env"
    MCP_TOOLS = "mcp_tools"


@dataclass(frozen=True)
class Rule:
    """One pattern + the verdict it produces.

    The id is the identifier used in audit JSONL and `permission_assertions`
    in eval cases. It is auto-derived from group + decision + pattern if the
    author does not supply one explicitly.
    """

    group: RuleGroup
    decision: DecisionType
    pattern: str
    reason: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            digest = hashlib.sha256(
                f"{self.group.value}:{self.decision.value}:{self.pattern}".encode()
            ).hexdigest()[:10]
            # frozen=True; use object.__setattr__ to assign post-init.
            object.__setattr__(
                self,
                "id",
                f"{self.group.value}.{self.decision.value}.{digest}",
            )


@dataclass
class Permissions:
    """Parsed `permissions.yaml` contents.

    The five rule lists are kept separate so the engine can short-circuit
    when a group has no rules. `defaults` is a per-group default verdict
    (allow / deny); falls back to `allow` at local/team and `deny` at org+
    when not declared.
    """

    skill: str = ""
    schema_version: str = "bulbasaur/v1"

    # Per-group default verdicts.
    defaults: dict[RuleGroup, DecisionType] = field(default_factory=dict)

    # Rule lists. Deny rules evaluate first; an allow rule cannot override.
    commands_allow: list[Rule] = field(default_factory=list)
    commands_deny: list[Rule] = field(default_factory=list)

    namespaces_allow: list[str] = field(default_factory=list)
    namespaces_deny: list[str] = field(default_factory=list)

    network_allow: list[Rule] = field(default_factory=list)
    network_deny: list[Rule] = field(default_factory=list)

    filesystem_read_paths: list[str] = field(default_factory=list)
    filesystem_write_paths: list[str] = field(default_factory=list)

    env_allow: list[str] = field(default_factory=list)
    env_redact: list[str] = field(default_factory=list)

    mcp_tools_allow: list[Rule] = field(default_factory=list)
    mcp_tools_deny: list[Rule] = field(default_factory=list)

    def default_for(self, group: RuleGroup) -> DecisionType:
        """Resolved default verdict for a group; falls back to ALLOW."""
        return self.defaults.get(group, DecisionType.ALLOW)


@dataclass(frozen=True)
class Decision:
    """Result of evaluating one op against the permissions.

    Carries the rule id that produced the verdict (or "default.<group>" when
    no rule matched and the group default applied). The reason is the
    matched rule's reason, or a one-line "no rule matched" explanation.
    """

    op_type: RuleGroup
    op_value: str
    decision: DecisionType
    rule_id: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == DecisionType.ALLOW

    @property
    def denied(self) -> bool:
        return self.decision == DecisionType.DENY


__all__ = ["Decision", "DecisionType", "Permissions", "Rule", "RuleGroup"]
