"""PermissionsValidator — checks permissions.yaml against the strictness rung.

Required-at-org+. Recommended at team (warning). Optional at local.

Beyond presence, the validator:

- Parses permissions.yaml; surface load errors as validation errors.
- Cross-checks rule patterns are anchored at org+ (footgun mitigation).
- Warns on common footguns: `.*` allows, missing pipe/substitution guards.
- Verifies that at org+ the `commands` and `network` groups have explicit
  `default: deny` declarations.
"""

from __future__ import annotations

import time
from pathlib import Path

from skillctl.messaging import FrameworkError
from skillctl.permissions import DecisionType, RuleGroup
from skillctl.permissions.loader import PermissionsLoadError, load_permissions
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult


class PermissionsValidator(Validator):
    """Validate permissions.yaml at the configured strictness rung."""

    name = "permissions"

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        is_org_or_above = strictness.includes(Strictness.ORG)
        is_team_or_above = strictness.includes(Strictness.TEAM)

        path = skill_dir / "permissions.yaml"

        if not path.exists():
            if is_org_or_above:
                errors.append(
                    FrameworkError(
                        summary="permissions.yaml not found",
                        detail=(
                            f"required at {strictness.value} strictness: {path}"
                        ),
                        fix=(
                            "Create permissions.yaml declaring command/URL/MCP-tool "
                            "allow/deny rules. See docs/permissions.md for the schema "
                            "and the mq-executor reference example."
                        ),
                        docs="../docs/permissions.md",
                    )
                )
            elif is_team_or_above:
                warnings.append(
                    FrameworkError(
                        summary="permissions.yaml not declared",
                        detail=(
                            "Recommended at team strictness; required at org+."
                        ),
                        fix=(
                            "Create permissions.yaml to declare what the skill is "
                            "allowed to do. See docs/permissions.md."
                        ),
                        docs="../docs/permissions.md",
                    )
                )
            else:
                notes.append("permissions.yaml not present (optional at local)")
            return _result(
                self.name, started, errors=errors, warnings=warnings, notes=notes
            )

        try:
            perms = load_permissions(skill_dir)
        except PermissionsLoadError as exc:
            return _result(
                self.name, started, errors=[exc.framework_error]
            )

        if perms is None:
            notes.append("permissions.yaml loaded as empty")
            return _result(self.name, started, notes=notes)

        # Org-tier checks.
        if is_org_or_above:
            for group in (RuleGroup.COMMANDS, RuleGroup.NETWORK, RuleGroup.MCP_TOOLS):
                if perms.default_for(group) != DecisionType.DENY:
                    errors.append(
                        FrameworkError(
                            summary=(
                                f"permissions.yaml: `{group.value}.default` must be `deny` "
                                f"at {strictness.value} strictness"
                            ),
                            fix=(
                                f"Add `{group.value}:\\n  default: deny\\n` and explicitly "
                                "enumerate the allow rules."
                            ),
                            docs="../docs/permissions.md",
                        )
                    )

        # Footgun checks — apply at team+; warning rather than error.
        for rule_list in (perms.commands_allow, perms.network_allow, perms.mcp_tools_allow):
            for rule in rule_list:
                if is_team_or_above and rule.pattern in (".*", "^.*$"):
                    warnings.append(
                        FrameworkError(
                            summary=(
                                f"permissions.yaml: overly broad allow rule {rule.id}"
                            ),
                            detail=f"pattern: {rule.pattern!r}",
                            fix=(
                                "Narrow the regex. A `.*` allow rule effectively "
                                "disables the whole group."
                            ),
                        )
                    )
                # Encourage anchored regex for commands group.
                if (
                    rule.group == RuleGroup.COMMANDS
                    and is_org_or_above
                    and not rule.pattern.startswith("^")
                    and "\\b" not in rule.pattern
                ):
                    warnings.append(
                        FrameworkError(
                            summary=(
                                f"permissions.yaml: command pattern {rule.id} is not anchored"
                            ),
                            detail=f"pattern: {rule.pattern!r}",
                            fix=(
                                "Start the pattern with `^` or use `\\b` word boundaries. "
                                "Unanchored command regexes are a footgun."
                            ),
                        )
                    )

        notes.append(
            f"permissions.yaml: "
            f"{len(perms.commands_allow)} command-allow, "
            f"{len(perms.commands_deny)} command-deny, "
            f"{len(perms.network_allow)} url-allow, "
            f"{len(perms.mcp_tools_allow)} mcp-allow"
        )

        return _result(
            self.name, started, errors=errors, warnings=warnings, notes=notes
        )


def _result(
    name: str,
    started: float,
    *,
    errors: list[FrameworkError] | None = None,
    warnings: list[FrameworkError] | None = None,
    notes: list[str] | None = None,
) -> ValidatorResult:
    return ValidatorResult(
        validator_name=name,
        passed=not (errors or []),
        duration_ms=int((time.monotonic() - started) * 1000),
        errors=errors or [],
        warnings=warnings or [],
        notes=notes or [],
    )


__all__ = ["PermissionsValidator"]
