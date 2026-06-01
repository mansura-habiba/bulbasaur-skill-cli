"""Guardrails — runtime engine that evaluates ops against Permissions.

Per the design in `docs/permissions.md`, every shell command, URL fetch, file
read/write, env var lookup, or MCP tool call gets evaluated through the
engine before the runtime performs it. The engine returns a Decision; the
caller refuses or proceeds.

This module is intentionally pure-Python and dependency-free so it can be
embedded in any AgentRuntime adapter without dragging the rest of bbsctl.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable

from .base import Decision, DecisionType, Permissions, Rule, RuleGroup

# Pre-compiled regex cache. Patterns load once at engine construction; deny
# evaluation is hot-path, so we compile up front.
_COMPILED_CACHE: dict[str, re.Pattern[str]] = {}


def _compile(pattern: str) -> re.Pattern[str]:
    cached = _COMPILED_CACHE.get(pattern)
    if cached is not None:
        return cached
    compiled = re.compile(pattern)
    _COMPILED_CACHE[pattern] = compiled
    return compiled


class Guardrails:
    """Evaluate runtime ops against a Permissions object.

    The class is stateless besides the Permissions reference; the cache of
    compiled patterns is module-level so multiple Guardrails instances over
    the same permissions share work.

    Each `evaluate_*` method returns a Decision. Callers refuse on denied,
    proceed on allowed. The Decision carries the rule_id that matched so
    the runtime can log it to audit JSONL.
    """

    def __init__(self, permissions: Permissions) -> None:
        self._perm = permissions
        # Eagerly compile so a bad pattern was caught at load time.
        for rule in self._all_rules():
            _compile(rule.pattern)

    def _all_rules(self) -> Iterable[Rule]:
        return (
            self._perm.commands_allow
            + self._perm.commands_deny
            + self._perm.network_allow
            + self._perm.network_deny
            + self._perm.mcp_tools_allow
            + self._perm.mcp_tools_deny
        )

    # ── command evaluation ──────────────────────────────────────────────

    def evaluate_command(self, command: str, *, namespace: str | None = None) -> Decision:
        """Evaluate a shell command line. Optional namespace pulled from `-n`.

        Order:
          1. Deny rules in commands_deny (first match wins → DENY).
          2. Namespace deny list (DENY).
          3. Allow rules in commands_allow (first match → ALLOW).
          4. Namespace allow list (only matters if the command would be denied
             by the default; an explicit allow-list of namespaces narrows the
             default-deny).
          5. Fall back to the group default.
        """
        for rule in self._perm.commands_deny:
            if _compile(rule.pattern).search(command):
                return Decision(
                    op_type=RuleGroup.COMMANDS,
                    op_value=command,
                    decision=DecisionType.DENY,
                    rule_id=rule.id,
                    reason=rule.reason or "matched commands.deny rule",
                )

        # Namespace check is its own group; surface as a separate rule_id.
        if namespace is not None:
            ns_decision = self._evaluate_namespace(namespace)
            if ns_decision.denied:
                return Decision(
                    op_type=RuleGroup.COMMANDS,
                    op_value=command,
                    decision=DecisionType.DENY,
                    rule_id=ns_decision.rule_id,
                    reason=ns_decision.reason,
                )

        for rule in self._perm.commands_allow:
            if _compile(rule.pattern).search(command):
                return Decision(
                    op_type=RuleGroup.COMMANDS,
                    op_value=command,
                    decision=DecisionType.ALLOW,
                    rule_id=rule.id,
                    reason=rule.reason or "matched commands.allow rule",
                )

        default = self._perm.default_for(RuleGroup.COMMANDS)
        return Decision(
            op_type=RuleGroup.COMMANDS,
            op_value=command,
            decision=default,
            rule_id=f"default.{RuleGroup.COMMANDS.value}",
            reason=f"no rule matched; group default = {default.value}",
        )

    def _evaluate_namespace(self, namespace: str) -> Decision:
        if namespace in self._perm.namespaces_deny:
            return Decision(
                op_type=RuleGroup.NAMESPACES,
                op_value=namespace,
                decision=DecisionType.DENY,
                rule_id=f"namespaces.deny.{namespace}",
                reason=f"namespace `{namespace}` is in deny list",
            )
        if self._perm.namespaces_allow:
            if namespace in self._perm.namespaces_allow:
                return Decision(
                    op_type=RuleGroup.NAMESPACES,
                    op_value=namespace,
                    decision=DecisionType.ALLOW,
                    rule_id=f"namespaces.allow.{namespace}",
                    reason=f"namespace `{namespace}` is in allow list",
                )
            return Decision(
                op_type=RuleGroup.NAMESPACES,
                op_value=namespace,
                decision=DecisionType.DENY,
                rule_id=f"namespaces.allow.miss.{namespace}",
                reason=(
                    f"namespace `{namespace}` is not in the allow list; "
                    "allow list is exclusive"
                ),
            )
        return Decision(
            op_type=RuleGroup.NAMESPACES,
            op_value=namespace,
            decision=DecisionType.ALLOW,
            rule_id="namespaces.no-rules",
            reason="no namespace rules declared",
        )

    # ── network evaluation ──────────────────────────────────────────────

    def evaluate_url(self, url: str) -> Decision:
        for rule in self._perm.network_deny:
            if _compile(rule.pattern).search(url):
                return Decision(
                    op_type=RuleGroup.NETWORK,
                    op_value=url,
                    decision=DecisionType.DENY,
                    rule_id=rule.id,
                    reason=rule.reason or "matched network.denied_sites rule",
                )
        for rule in self._perm.network_allow:
            if _compile(rule.pattern).search(url):
                return Decision(
                    op_type=RuleGroup.NETWORK,
                    op_value=url,
                    decision=DecisionType.ALLOW,
                    rule_id=rule.id,
                    reason=rule.reason or "matched network.allowed_sites rule",
                )
        default = self._perm.default_for(RuleGroup.NETWORK)
        return Decision(
            op_type=RuleGroup.NETWORK,
            op_value=url,
            decision=default,
            rule_id=f"default.{RuleGroup.NETWORK.value}",
            reason=f"no rule matched; group default = {default.value}",
        )

    # ── filesystem evaluation ───────────────────────────────────────────

    def evaluate_read(self, path: str) -> Decision:
        return self._evaluate_fs(
            path, allowed=self._perm.filesystem_read_paths, mode="read"
        )

    def evaluate_write(self, path: str) -> Decision:
        return self._evaluate_fs(
            path, allowed=self._perm.filesystem_write_paths, mode="write"
        )

    def _evaluate_fs(self, path: str, *, allowed: list[str], mode: str) -> Decision:
        # Filesystem is glob-based, not regex.
        for pat in allowed:
            if fnmatch.fnmatchcase(path, pat):
                return Decision(
                    op_type=RuleGroup.FILESYSTEM,
                    op_value=path,
                    decision=DecisionType.ALLOW,
                    rule_id=f"filesystem.{mode}.allow",
                    reason=f"path matches {mode}_paths glob `{pat}`",
                )
        # Filesystem default is deny when allow-list is present and the path
        # did not match; allow when the allow-list is empty (no rules == no
        # restriction).
        if not allowed:
            return Decision(
                op_type=RuleGroup.FILESYSTEM,
                op_value=path,
                decision=DecisionType.ALLOW,
                rule_id=f"filesystem.{mode}.no-rules",
                reason=f"no {mode}_paths rules declared",
            )
        return Decision(
            op_type=RuleGroup.FILESYSTEM,
            op_value=path,
            decision=DecisionType.DENY,
            rule_id=f"filesystem.{mode}.deny",
            reason=f"path not in {mode}_paths allow list",
        )

    # ── env evaluation ──────────────────────────────────────────────────

    def evaluate_env(self, name: str) -> Decision:
        if self._perm.env_allow and name in self._perm.env_allow:
            return Decision(
                op_type=RuleGroup.ENV,
                op_value=name,
                decision=DecisionType.ALLOW,
                rule_id=f"env.allow.{name}",
                reason="env var is in allow list",
            )
        # Empty allow list == no restriction.
        if not self._perm.env_allow:
            return Decision(
                op_type=RuleGroup.ENV,
                op_value=name,
                decision=DecisionType.ALLOW,
                rule_id="env.no-rules",
                reason="no env rules declared",
            )
        return Decision(
            op_type=RuleGroup.ENV,
            op_value=name,
            decision=DecisionType.DENY,
            rule_id="env.allow.miss",
            reason=f"env var `{name}` not in allow list",
        )

    def should_redact(self, name: str) -> bool:
        """Check whether the named env var should be redacted in audit logs."""
        for pat in self._perm.env_redact:
            try:
                if re.search(pat, name):
                    return True
            except re.error:
                # Invalid redact pattern; redact defensively.
                if pat in name:
                    return True
        return False

    # ── mcp tool evaluation ─────────────────────────────────────────────

    def evaluate_mcp_tool(self, tool_name: str) -> Decision:
        """Evaluate `<server>.<tool>` against the mcp_tools rules."""
        for rule in self._perm.mcp_tools_deny:
            if _compile(rule.pattern).search(tool_name):
                return Decision(
                    op_type=RuleGroup.MCP_TOOLS,
                    op_value=tool_name,
                    decision=DecisionType.DENY,
                    rule_id=rule.id,
                    reason=rule.reason or "matched mcp_tools.deny rule",
                )
        for rule in self._perm.mcp_tools_allow:
            if _compile(rule.pattern).search(tool_name):
                return Decision(
                    op_type=RuleGroup.MCP_TOOLS,
                    op_value=tool_name,
                    decision=DecisionType.ALLOW,
                    rule_id=rule.id,
                    reason=rule.reason or "matched mcp_tools.allow rule",
                )
        default = self._perm.default_for(RuleGroup.MCP_TOOLS)
        return Decision(
            op_type=RuleGroup.MCP_TOOLS,
            op_value=tool_name,
            decision=default,
            rule_id=f"default.{RuleGroup.MCP_TOOLS.value}",
            reason=f"no rule matched; group default = {default.value}",
        )

    # ── namespace pull helper ───────────────────────────────────────────

    @staticmethod
    def extract_namespace(command: str) -> str | None:
        """Pull `-n <namespace>` or `--namespace <ns>` from a command line."""
        match = re.search(r"(?:^|\s)(?:-n|--namespace)[\s=]+([a-z0-9-]+)", command)
        return match.group(1) if match else None


__all__ = ["Guardrails"]
