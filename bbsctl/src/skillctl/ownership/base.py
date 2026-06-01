"""Ownership data model.

Schema (matches docs/strictness-levels.md ownership requirements):

    schema_version: bulbasaur/v1
    skill: mq-executor
    team: mq-platform
    contact: mq-platform@example.com           # email or Slack channel
    runbook: https://wiki.example.com/runbooks/mq-restart
    on_call:
      rotation: pagerduty:mq-platform-primary  # opaque-string per system
      escalation_minutes: 15
    escalation:
      - tier: 1
        contact: oncall-primary@example.com
        within_minutes: 0
      - tier: 2
        contact: manager@example.com
        within_minutes: 30
    cost_owner: cost-center-1234                # FinOps account id
    business_owner: jane.doe@example.com        # decision authority
    last_reviewed: 2026-05-30                   # ISO date

At `team` strictness, only `team` and `contact` are required.
At `org` strictness, the full schema above is required.
At `regulated`, plus `last_reviewed` must be within the retention SLA window
(default: 365 days; configurable in skill.yaml).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class OnCall:
    """On-call rotation reference. Opaque-string per paging system."""

    rotation: str = ""
    escalation_minutes: int = 15


@dataclass(frozen=True)
class Escalation:
    """One tier of escalation. Sorted by tier ascending at runtime."""

    tier: int
    contact: str
    within_minutes: int = 0


@dataclass
class Ownership:
    """Full ownership.yaml content. Maps to docs/strictness-levels.md.

    Required at `team`+ strictness; the validator decides what subset is
    required per rung.
    """

    skill: str = ""
    schema_version: str = "bulbasaur/v1"

    # Required at team+:
    team: str = ""
    contact: str = ""

    # Recommended at team; required at org+:
    runbook: str = ""

    # Required at org+:
    on_call: OnCall | None = None
    escalation: list[Escalation] = field(default_factory=list)
    cost_owner: str = ""
    business_owner: str = ""

    # Required at regulated; carries the date of last review for retention checks.
    last_reviewed: date | None = None

    @property
    def has_team_minimum(self) -> bool:
        return bool(self.team and self.contact)

    @property
    def has_org_minimum(self) -> bool:
        return (
            self.has_team_minimum
            and bool(self.runbook)
            and self.on_call is not None
            and bool(self.escalation)
            and bool(self.cost_owner)
            and bool(self.business_owner)
        )


__all__ = ["Escalation", "OnCall", "Ownership"]
