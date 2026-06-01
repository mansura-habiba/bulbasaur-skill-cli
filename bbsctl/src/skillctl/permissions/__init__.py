"""Skill permissions — `permissions.yaml`.

The skill artifact declaring what a skill is allowed to do at runtime. Sibling
to `SKILL.md` and `skill.yaml`. Enforced at four points in the lifecycle:

  Compile-time  — PermissionsLintStep validates the file and flags footguns.
  Validate      — PermissionsValidator checks the rules satisfy the strictness rung.
  Publish gate  — refuses to host a skill at `org+` without a valid permissions.yaml.
  Runtime       — Guardrails engine evaluates every op against the merged rules.

See: docs/permissions.md for the full design.
"""

from .base import (
    Decision,
    DecisionType,
    Permissions,
    Rule,
    RuleGroup,
)
from .engine import Guardrails
from .loader import PermissionsLoadError, load_permissions, merge_permissions

__all__ = [
    "Decision",
    "DecisionType",
    "Guardrails",
    "Permissions",
    "PermissionsLoadError",
    "Rule",
    "RuleGroup",
    "load_permissions",
    "merge_permissions",
]
