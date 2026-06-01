"""Ownership — `ownership.yaml`.

The skill artifact that names who owns the skill. Optional at `local`,
recommended at `team` (warning if missing), **required at `org`+**.

`OwnershipRef` (the stub in `skill_yaml.py`) carries the minimum
team/contact/runbook fields embedded in `skill.yaml` at `team` strictness.
This module ships the full `ownership.yaml` artifact for `org`+, with
escalation, on-call, and SLA fields.

See: docs/strictness-levels.md (ownership row of the matrix).
"""

from .base import Escalation, OnCall, Ownership
from .loader import OwnershipLoadError, load_ownership

__all__ = [
    "Escalation",
    "OnCall",
    "Ownership",
    "OwnershipLoadError",
    "load_ownership",
]
