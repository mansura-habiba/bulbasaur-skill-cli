from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import assert_never

from skillctl.permissions.base import Decision, DecisionType, Permissions, RuleGroup
from skillctl.permissions.engine import Guardrails, fs_list_is_open
from skillctl.permissions.loader import PermissionsLoadError, load_permissions
from skillctl.risk_matrix import get_matrix_cell
from skillctl.skill_yaml import Risk, SideEffects, SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness


class OpKind(Enum):
    """One runtime operation kind and the rungs granting it costs.

    Members are (token, group, bounded rung, unbounded rung). Bounded means
    an allow list admits some ops. Unbounded means the group default, or a
    missing key, admits every op.
    """

    ENV = ("env", RuleGroup.ENV, SideEffects.NONE, SideEffects.NONE)
    READ = ("read", RuleGroup.FILESYSTEM, SideEffects.READ_ONLY, SideEffects.READ_ONLY)
    WRITE = ("write", RuleGroup.FILESYSTEM, SideEffects.REVERSIBLE, SideEffects.DESTRUCTIVE)
    COMMAND = ("command", RuleGroup.COMMANDS, SideEffects.READ_ONLY, SideEffects.DESTRUCTIVE)
    URL = ("url", RuleGroup.NETWORK, SideEffects.EXTERNAL, SideEffects.EXTERNAL)
    MCP_TOOL = ("mcp_tool", RuleGroup.MCP_TOOLS, SideEffects.EXTERNAL, SideEffects.EXTERNAL)

    def __init__(
        self,
        token: str,
        group: RuleGroup,
        bounded: SideEffects,
        unbounded: SideEffects,
    ) -> None:
        self.token = token
        self.group = group
        self.bounded = bounded
        self.unbounded = unbounded

    @classmethod
    def parse(cls, token: str) -> OpKind | None:
        for kind in cls:
            if kind.token == token:
                return kind
        return None


@dataclass(frozen=True)
class Grant:
    kind: OpKind
    bounded: bool
    source: str
    # True only for a bounded commands.allow regex. Validate notes it unverified.
    command_regex_unverified: bool = False

    @property
    def rung(self) -> SideEffects:
        return self.kind.bounded if self.bounded else self.kind.unbounded


@dataclass(frozen=True)
class ImpliedSideEffects:
    grants: tuple[Grant, ...]
    from_file: bool

    @property
    def rung(self) -> SideEffects | None:
        """Highest grant when from_file. None when permissions.yaml was not loaded."""
        if not self.from_file:
            return None
        if not self.grants:
            return SideEffects.NONE
        return max(self.grants, key=lambda grant: grant.rung.rank).rung

    @property
    def label(self) -> str:
        if not self.from_file:
            return "unverified"
        assert self.rung is not None
        return self.rung.value

    def exceeding(self, declared: SideEffects) -> tuple[Grant, ...]:
        return tuple(grant for grant in self.grants if grant.rung.rank > declared.rank)

    def grant_for(self, kind: OpKind) -> Grant | None:
        for grant in self.grants:
            if grant.kind is kind:
                return grant
        return None


def implied_side_effects(permissions: Permissions | None) -> ImpliedSideEffects:
    if permissions is None:
        return ImpliedSideEffects(grants=(), from_file=False)
    grants = tuple(
        grant for kind in OpKind if (grant := _grant(permissions, kind)) is not None
    )
    return ImpliedSideEffects(grants=grants, from_file=True)


def _grant(perm: Permissions, kind: OpKind) -> Grant | None:
    match kind:
        case OpKind.ENV:
            return None
        case OpKind.READ:
            return _fs_grant(kind, perm.filesystem_read_paths, "read_paths")
        case OpKind.WRITE:
            return _fs_grant(kind, perm.filesystem_write_paths, "write_paths")
        case OpKind.COMMAND:
            return _rule_grant(
                kind,
                default_allow=perm.default_for(RuleGroup.COMMANDS) == DecisionType.ALLOW,
                rules=perm.commands_allow,
                open_source="commands.default",
                bounded_source="commands.allow",
                command_regex_unverified=True,
            )
        case OpKind.URL:
            return _rule_grant(
                kind,
                default_allow=perm.default_for(RuleGroup.NETWORK) == DecisionType.ALLOW,
                rules=perm.network_allow,
                open_source="network.default",
                bounded_source="network.allowed_sites",
                command_regex_unverified=False,
            )
        case OpKind.MCP_TOOL:
            return _rule_grant(
                kind,
                default_allow=perm.default_for(RuleGroup.MCP_TOOLS) == DecisionType.ALLOW,
                rules=perm.mcp_tools_allow,
                open_source="mcp_tools.default",
                bounded_source="mcp_tools.allow",
                command_regex_unverified=False,
            )
        case _:
            assert_never(kind)


def _fs_grant(kind: OpKind, paths: list[str] | None, key: str) -> Grant | None:
    if not fs_list_is_open(paths):
        return None
    if paths is None:
        return Grant(kind, bounded=False, source=f"filesystem.{key}")
    return Grant(kind, bounded=True, source=f"filesystem.{key}={paths!r}")


def _rule_grant(
    kind: OpKind,
    *,
    default_allow: bool,
    rules: list[object],
    open_source: str,
    bounded_source: str,
    command_regex_unverified: bool,
) -> Grant | None:
    if default_allow:
        return Grant(kind, bounded=False, source=open_source)
    if rules:
        return Grant(
            kind,
            bounded=True,
            source=bounded_source,
            command_regex_unverified=command_regex_unverified,
        )
    return None


def undeclared_blocks(strictness: Strictness, risk: Risk) -> bool:
    if strictness.includes(Strictness.ORG):
        return True
    return _matrix_cap(strictness, risk) is not None


def _matrix_cap(strictness: Strictness, risk: Risk) -> SideEffects | None:
    if risk.level is None:
        return None
    raw = get_matrix_cell(strictness, risk.level).max_side_effects
    if not raw:
        return None
    return SideEffects.from_string(raw)


@dataclass(frozen=True)
class _Block:
    rule_id: str
    reason: str


class SideEffectCeiling:
    def __init__(
        self,
        permissions: Permissions,
        declared: SideEffects | None,
        *,
        blocked: _Block | None = None,
        permissions_from_file: bool = True,
    ) -> None:
        self._guardrails = Guardrails(permissions)
        self._declared = declared
        self._blocked = blocked
        if permissions_from_file:
            self._implied = implied_side_effects(permissions)
        else:
            self._implied = ImpliedSideEffects(grants=(), from_file=False)

    @classmethod
    def for_skill(cls, skill_dir: Path, strictness: Strictness) -> SideEffectCeiling:
        try:
            overlay = load_skill_yaml(skill_dir)
        except SkillYamlError as exc:
            return cls._closed("side_effects.unloadable", exc.framework_error.summary)
        try:
            perms = load_permissions(skill_dir)
        except PermissionsLoadError as exc:
            return cls._closed("side_effects.unloadable", exc.framework_error.summary)

        declared = overlay.risk.side_effects if overlay is not None else None
        unrecognized = overlay.risk.side_effects_unrecognized if overlay is not None else ""
        from_file = perms is not None
        permissions = perms if perms is not None else Permissions()

        if not from_file and strictness.includes(Strictness.ORG):
            return cls(
                permissions,
                declared,
                blocked=_Block(
                    "side_effects.no-permissions",
                    "permissions.yaml is absent",
                ),
                permissions_from_file=False,
            )
        if unrecognized:
            return cls(
                permissions,
                None,
                blocked=_Block(
                    "side_effects.unrecognized",
                    f"unrecognized side_effects token {unrecognized!r}",
                ),
                permissions_from_file=from_file,
            )
        if declared is None:
            return cls(
                permissions,
                None,
                blocked=_Block(
                    "side_effects.undeclared",
                    "risk.side_effects is not set",
                ),
                permissions_from_file=from_file,
            )
        return cls(permissions, declared, permissions_from_file=from_file)

    @classmethod
    def _closed(cls, rule_id: str, reason: str) -> SideEffectCeiling:
        return cls(
            Permissions(),
            None,
            blocked=_Block(rule_id, reason),
            permissions_from_file=False,
        )

    def evaluate(self, kind: OpKind, value: str) -> Decision:
        """Allow or deny one operation.

        Guardrails runs first so a permissions deny keeps its rule_id.
        The ceiling then refuses an allowed op whose granted rung outranks
        the declaration. A missing or unrecognized declaration denies here
        and is never treated as destructive.
        """
        if self._blocked is not None:
            return _deny(kind, value, self._blocked.rule_id, self._blocked.reason)
        try:
            decision = _dispatch(self._guardrails, kind, value)
        except Exception as exc:
            return _deny(
                kind,
                value,
                "side_effects.error",
                f"guardrails raised {type(exc).__name__}: {exc}",
            )
        if decision.denied:
            return decision
        if self._declared is None:
            return _deny(kind, value, "side_effects.undeclared", "risk.side_effects is not set")
        rung = self._granted_rung(kind)
        if rung is not None and rung.rank > self._declared.rank:
            return _deny(
                kind,
                value,
                f"side_effects.ceiling.{kind.token}",
                f"{kind.token} implies {rung.value} > declared {self._declared.value}",
            )
        return decision

    def _granted_rung(self, kind: OpKind) -> SideEffects | None:
        if not self._implied.from_file:
            return kind.unbounded
        grant = self._implied.grant_for(kind)
        if grant is None:
            return None
        return grant.rung

    @property
    def declared(self) -> SideEffects | None:
        return self._declared

    @property
    def implied(self) -> ImpliedSideEffects:
        return self._implied


def _dispatch(guardrails: Guardrails, kind: OpKind, value: str) -> Decision:
    match kind:
        case OpKind.COMMAND:
            return guardrails.evaluate_command(
                value, namespace=Guardrails.extract_namespace(value)
            )
        case OpKind.URL:
            return guardrails.evaluate_url(value)
        case OpKind.READ:
            return guardrails.evaluate_read(value)
        case OpKind.WRITE:
            return guardrails.evaluate_write(value)
        case OpKind.ENV:
            return guardrails.evaluate_env(value)
        case OpKind.MCP_TOOL:
            return guardrails.evaluate_mcp_tool(value)
        case _:
            assert_never(kind)


def _deny(kind: OpKind, value: str, rule_id: str, reason: str) -> Decision:
    return Decision(
        op_type=kind.group,
        op_value=value,
        decision=DecisionType.DENY,
        rule_id=rule_id,
        reason=reason,
    )


__all__ = ["OpKind", "SideEffectCeiling", "implied_side_effects"]
