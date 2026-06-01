"""Load `ownership.yaml`.

Tolerant on optional fields, strict on the field types it knows about. The
validator (separate module) decides what is required per strictness rung.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError

from .base import Escalation, OnCall, Ownership

_OWNERSHIP_YAML_NAME = "ownership.yaml"


class OwnershipLoadError(Exception):
    """Raised when ownership.yaml is unparseable.

    Carries a FrameworkError for the caller to emit.
    """

    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


def load_ownership(skill_dir: Path) -> Ownership | None:
    """Load `ownership.yaml` from `skill_dir`.

    Returns None if the file is absent — strictness validators decide
    whether that is fatal.
    """
    path = skill_dir / _OWNERSHIP_YAML_NAME
    if not path.exists():
        return None

    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path)
    except Exception as exc:
        raise OwnershipLoadError(
            FrameworkError(
                summary="ownership.yaml: YAML parse error",
                detail=str(exc),
                fix="Fix the YAML syntax. See docs/strictness-levels.md for the schema.",
                docs="../docs/strictness-levels.md",
            )
        ) from exc

    if not isinstance(raw, dict):
        raise OwnershipLoadError(
            FrameworkError(
                summary="ownership.yaml: top-level must be a mapping",
                fix="Start with `schema_version: bulbasaur/v1` and `skill: <name>`.",
            )
        )

    return _parse(raw, path=path)


def _parse(raw: dict[str, Any], *, path: Path) -> Ownership:
    on_call: OnCall | None = None
    if (oc := raw.get("on_call")) and isinstance(oc, dict):
        on_call = OnCall(
            rotation=str(oc.get("rotation") or ""),
            escalation_minutes=_safe_int(oc.get("escalation_minutes"), default=15),
        )

    escalation: list[Escalation] = []
    if (raw_esc := raw.get("escalation")) and isinstance(raw_esc, list):
        for i, entry in enumerate(raw_esc):
            if not isinstance(entry, dict):
                raise OwnershipLoadError(
                    FrameworkError(
                        summary=(
                            f"ownership.yaml: `escalation[{i}]` must be a mapping"
                        ),
                        detail=f"path: {path}",
                        fix="Each entry is `{tier, contact, within_minutes}`.",
                    )
                )
            tier_raw = entry.get("tier")
            if tier_raw is None:
                raise OwnershipLoadError(
                    FrameworkError(
                        summary=(
                            f"ownership.yaml: `escalation[{i}]` missing `tier`"
                        ),
                        fix="Add `tier: <int>` (1 = primary, 2 = secondary, etc.).",
                    )
                )
            contact = entry.get("contact")
            if not contact or not isinstance(contact, str):
                raise OwnershipLoadError(
                    FrameworkError(
                        summary=(
                            f"ownership.yaml: `escalation[{i}]` missing `contact`"
                        ),
                        fix="Add `contact: <email-or-channel>`.",
                    )
                )
            escalation.append(
                Escalation(
                    tier=_safe_int(tier_raw, default=99),
                    contact=contact,
                    within_minutes=_safe_int(entry.get("within_minutes"), default=0),
                )
            )
        # Stable order by tier; downstream code can rely on ascending tiers.
        escalation.sort(key=lambda e: e.tier)

    last_reviewed = _parse_date(raw.get("last_reviewed"), path=path)

    return Ownership(
        skill=str(raw.get("skill") or ""),
        schema_version=str(raw.get("schema_version") or "bulbasaur/v1"),
        team=str(raw.get("team") or ""),
        contact=str(raw.get("contact") or ""),
        runbook=str(raw.get("runbook") or ""),
        on_call=on_call,
        escalation=escalation,
        cost_owner=str(raw.get("cost_owner") or ""),
        business_owner=str(raw.get("business_owner") or ""),
        last_reviewed=last_reviewed,
    )


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any, *, path: Path) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise OwnershipLoadError(
                FrameworkError(
                    summary=f"ownership.yaml: `last_reviewed` must be ISO date",
                    detail=f"path: {path}; got: {value!r}",
                    fix="Use `YYYY-MM-DD` format (e.g. `last_reviewed: 2026-05-30`).",
                )
            ) from exc
    return None


__all__ = ["OwnershipLoadError", "load_ownership"]
