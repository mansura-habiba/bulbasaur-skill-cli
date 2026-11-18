"""PermissionsHook — thin pre-tool seam over SideEffectCeiling.

This is not the full Phase-4 hook bus. Adapters call ``check`` before a tool
runs. The ceiling applies Guardrails plus the declared side_effects rung, and
optional audit JSONL records the decision.
"""

from __future__ import annotations

from pathlib import Path

from skillctl.audit.stream import append_audit_event
from skillctl.permissions.base import Decision
from skillctl.permissions.side_effects import OpKind, SideEffectCeiling
from skillctl.strictness import Strictness


class PermissionsHook:
    def __init__(
        self,
        ceiling: SideEffectCeiling,
        *,
        audit_sink: Path | str | None = None,
        skill: str = "",
    ) -> None:
        self._ceiling = ceiling
        self._audit_sink = audit_sink
        self._skill = skill

    @classmethod
    def for_skill(
        cls,
        skill_dir: Path,
        strictness: Strictness,
        *,
        audit_sink: Path | str | None = None,
    ) -> PermissionsHook:
        return cls(
            SideEffectCeiling.for_skill(skill_dir, strictness),
            audit_sink=audit_sink,
            skill=skill_dir.name,
        )

    def check(self, kind: OpKind, value: str) -> Decision:
        decision = self._ceiling.evaluate(kind, value)
        if decision.denied and decision.rule_id.startswith("side_effects."):
            event = "skill.side_effects.ceiling_denied"
        elif decision.denied:
            event = "permission_denied"
        else:
            event = "permission_allowed"
        append_audit_event(
            self._audit_sink,
            event,
            payload={
                "skill": self._skill,
                "kind": kind.token,
                "op_value": value,
                "decision": decision.decision.value,
                "rule_id": decision.rule_id,
                "reason": decision.reason,
            },
        )
        return decision


__all__ = ["PermissionsHook"]
