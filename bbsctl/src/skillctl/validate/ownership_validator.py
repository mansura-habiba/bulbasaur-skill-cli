"""OwnershipValidator — checks ownership.yaml against the strictness rung.

- local      ownership.yaml optional
- team       ownership.yaml recommended; OwnershipRef in skill.yaml acceptable
- org        ownership.yaml required with full schema
- regulated  ownership.yaml required; `last_reviewed` must be < retention window
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

from skillctl.messaging import FrameworkError
from skillctl.ownership.loader import OwnershipLoadError, load_ownership
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult

# At regulated, last_reviewed must be within this many days.
_REGULATED_REVIEW_WINDOW_DAYS = 365


class OwnershipValidator(Validator):
    """Validate ownership artifacts at the configured strictness rung."""

    name = "ownership"

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        is_org_or_above = strictness.includes(Strictness.ORG)
        is_team_or_above = strictness.includes(Strictness.TEAM)
        is_regulated = strictness.includes(Strictness.REGULATED)

        # Load ownership.yaml if present.
        try:
            ownership = load_ownership(skill_dir)
        except OwnershipLoadError as exc:
            return _result(self.name, started, errors=[exc.framework_error])

        # If ownership.yaml absent, fall back to OwnershipRef inside skill.yaml at team.
        if ownership is None:
            if is_org_or_above:
                errors.append(
                    FrameworkError(
                        summary="ownership.yaml not found",
                        detail=(
                            f"required at {strictness.value} strictness "
                            f"(expected at {skill_dir / 'ownership.yaml'})"
                        ),
                        fix=(
                            "Create ownership.yaml with team, contact, runbook, "
                            "on_call, escalation, cost_owner, business_owner. "
                            "See docs/strictness-levels.md."
                        ),
                        docs="../docs/strictness-levels.md",
                    )
                )
                return _result(self.name, started, errors=errors)
            if is_team_or_above:
                # OwnershipRef in skill.yaml is acceptable at team.
                try:
                    overlay = load_skill_yaml(skill_dir)
                except SkillYamlError:
                    overlay = None
                if overlay is not None and overlay.has_ownership:
                    notes.append(
                        f"ownership declared in skill.yaml: team={overlay.ownership.team!r}"
                    )
                    return _result(self.name, started, notes=notes)
                warnings.append(
                    FrameworkError(
                        summary="ownership not declared",
                        detail=(
                            "Recommended at team strictness; required at org+."
                        ),
                        fix=(
                            "Create ownership.yaml or add an `ownership:` block to "
                            "skill.yaml. See docs/strictness-levels.md."
                        ),
                    )
                )
                return _result(self.name, started, warnings=warnings)
            notes.append("ownership.yaml not present (optional at local)")
            return _result(self.name, started, notes=notes)

        # ownership.yaml loaded — validate per rung.
        if is_team_or_above and not ownership.has_team_minimum:
            errors.append(
                FrameworkError(
                    summary="ownership.yaml: missing team-tier minimum fields",
                    detail="required: `team` and `contact`",
                    fix="Add `team:` and `contact:` to ownership.yaml.",
                    docs="../docs/strictness-levels.md",
                )
            )

        if is_org_or_above and not ownership.has_org_minimum:
            missing = _missing_org_fields(ownership)
            errors.append(
                FrameworkError(
                    summary=(
                        f"ownership.yaml: missing org-tier required fields: "
                        f"{', '.join(missing)}"
                    ),
                    fix=(
                        f"Add the missing fields to ownership.yaml: "
                        f"{', '.join(missing)}. See docs/strictness-levels.md."
                    ),
                    docs="../docs/strictness-levels.md",
                )
            )

        if is_regulated:
            if ownership.last_reviewed is None:
                errors.append(
                    FrameworkError(
                        summary="ownership.yaml: `last_reviewed` required at regulated strictness",
                        fix="Add `last_reviewed: YYYY-MM-DD` recording the most recent review.",
                    )
                )
            else:
                age = date.today() - ownership.last_reviewed
                if age > timedelta(days=_REGULATED_REVIEW_WINDOW_DAYS):
                    errors.append(
                        FrameworkError(
                            summary=(
                                f"ownership.yaml: `last_reviewed` is {age.days} days old; "
                                f"must be within {_REGULATED_REVIEW_WINDOW_DAYS} days at "
                                f"regulated strictness"
                            ),
                            fix=(
                                "Run an ownership review and update "
                                "`last_reviewed:` to today's date."
                            ),
                        )
                    )

        if not errors:
            notes.append(
                f"ownership.yaml: team={ownership.team!r}, "
                f"escalation_tiers={len(ownership.escalation)}"
            )

        return _result(
            self.name, started, errors=errors, warnings=warnings, notes=notes
        )


def _missing_org_fields(o) -> list[str]:
    missing: list[str] = []
    if not o.team:
        missing.append("team")
    if not o.contact:
        missing.append("contact")
    if not o.runbook:
        missing.append("runbook")
    if o.on_call is None:
        missing.append("on_call")
    if not o.escalation:
        missing.append("escalation")
    if not o.cost_owner:
        missing.append("cost_owner")
    if not o.business_owner:
        missing.append("business_owner")
    return missing


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


__all__ = ["OwnershipValidator"]
