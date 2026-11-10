from __future__ import annotations

import time
from pathlib import Path
from typing import assert_never

from skillctl.audit.stream import append_audit_event, resolve_audit_sink
from skillctl.messaging import FrameworkError
from skillctl.permissions.loader import PermissionsLoadError, load_permissions
from skillctl.permissions.side_effects import (
    Grant,
    ImpliedSideEffects,
    OpKind,
    implied_side_effects,
    undeclared_blocks,
)
from skillctl.risk_matrix import get_matrix_cell
from skillctl.skill_yaml import Risk, SideEffects, SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult


class SideEffectsValidator(Validator):
    name = "side-effects"

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        try:
            overlay = load_skill_yaml(skill_dir)
        except SkillYamlError as exc:
            return _result(self.name, started, errors=[exc.framework_error])

        if overlay is None:
            notes.append("no skill.yaml — side-effects check skipped")
            return _result(self.name, started, notes=notes)

        risk = overlay.risk
        cap = _cap(strictness, risk)
        perms = None
        load_failed = False
        line = "declared=(unset) implied=unverified cap=(none)"
        try:
            perms = load_permissions(skill_dir)
        except PermissionsLoadError:
            load_failed = True
        implied = implied_side_effects(perms)
        line = _contract_line(risk, implied, cap, strictness)
        if load_failed:
            notes.append(f"permissions.yaml could not be loaded; {line}")

        if risk.side_effects_unrecognized:
            errors.append(
                FrameworkError(
                    summary=(
                        "side-effects: unrecognized `side_effects` token "
                        f"`{risk.side_effects_unrecognized}`"
                    ),
                    detail=line,
                    fix=(
                        "Set `risk.side_effects` to one of: none, read_only, "
                        "reversible, external, destructive."
                    ),
                )
            )
        elif risk.side_effects is None:
            finding = FrameworkError(
                summary="side-effects: `risk.side_effects` is not set",
                detail=line,
                fix=(
                    "Declare `risk.side_effects` as none, read_only, reversible, "
                    "external, or destructive."
                ),
            )
            if undeclared_blocks(strictness, risk):
                errors.append(finding)
            elif strictness.includes(Strictness.TEAM):
                warnings.append(finding)
            else:
                notes.append(f"side-effects: {line}")
        elif not load_failed and not implied.from_file:
            finding = FrameworkError(
                summary="side-effects: permissions.yaml absent; implied=unverified",
                detail=line,
                fix="Add permissions.yaml so the declaration can be checked against real grants.",
            )
            if strictness.includes(Strictness.TEAM):
                warnings.append(finding)
            else:
                notes.append(f"side-effects: {line}")
        elif implied.from_file and risk.side_effects is not None:
            declared = risk.side_effects
            for grant in implied.exceeding(declared):
                errors.append(_exceeding_finding(grant, declared, line))
            unverified = [
                grant for grant in implied.grants if grant.command_regex_unverified
            ]
            if unverified:
                notes.append(
                    f"commands: {len(unverified)} allow rules scored as "
                    f"{unverified[0].rung.value} (unverified)"
                )
            if not errors:
                notes.append(f"side-effects: {line}")

        result = _result(
            self.name, started, errors=errors, warnings=warnings, notes=notes
        )
        if resolve_audit_sink() is not None:
            append_audit_event(
                None,
                "skill.side_effects.validated",
                payload={
                    "skill": skill_dir.name,
                    "passed": result.passed,
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                    "detail": line,
                },
            )
        return result


def _cap(strictness: Strictness, risk: Risk) -> SideEffects | None:
    if risk.level is None:
        return None
    raw = get_matrix_cell(strictness, risk.level).max_side_effects
    if not raw:
        return None
    return SideEffects.from_string(raw)


def _contract_line(
    risk: Risk,
    implied: ImpliedSideEffects,
    cap: SideEffects | None,
    strictness: Strictness,
) -> str:
    if risk.side_effects_unrecognized:
        declared = risk.side_effects_unrecognized
    elif risk.side_effects is None:
        declared = "(missing)"
    else:
        declared = risk.side_effects.value
    level = risk.level.value if risk.level is not None else "unset"
    if cap is None:
        cap_text = f"(none at {strictness.value}/{level})"
    else:
        cap_text = f"{cap.value} (risk-matrix {strictness.value}/{level})"
    return f"declared={declared} implied={implied.label} cap={cap_text}"


def _exceeding_finding(grant: Grant, declared: SideEffects, line: str) -> FrameworkError:
    return FrameworkError(
        summary=(
            f"side-effects: `{grant.source}` allows {_allows_phrase(grant)} "
            f"but `side_effects` is `{declared.value}`"
        ),
        detail=f"{line}; {grant.kind.token} → {grant.rung.value} ({grant.source})",
        fix=f"{_narrow(grant)}, or raise `risk.side_effects` to `{grant.rung.value}`.",
    )


def _allows_phrase(grant: Grant) -> str:
    match grant.kind:
        case OpKind.WRITE:
            return "writes"
        case OpKind.READ:
            return "reads"
        case OpKind.COMMAND:
            return "listed commands" if grant.bounded else "any command"
        case OpKind.URL:
            return "listed URLs" if grant.bounded else "any URL"
        case OpKind.MCP_TOOL:
            return "listed MCP tools" if grant.bounded else "any MCP tool"
        case OpKind.ENV:
            return "env reads"
        case _:
            assert_never(grant.kind)


def _narrow(grant: Grant) -> str:
    match grant.kind:
        case OpKind.WRITE:
            return "Set `filesystem.write_paths: []`"
        case OpKind.READ:
            return "Set `filesystem.read_paths: []`"
        case OpKind.COMMAND:
            return "Set `commands: {default: deny}` and remove allow rules"
        case OpKind.URL:
            return "Add `network: {default: deny}`"
        case OpKind.MCP_TOOL:
            return "Add `mcp_tools: {default: deny}`"
        case OpKind.ENV:
            return "Narrow env.allow"
        case _:
            assert_never(grant.kind)


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


__all__ = ["SideEffectsValidator"]
