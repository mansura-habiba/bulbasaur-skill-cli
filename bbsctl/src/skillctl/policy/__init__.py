"""Policy — data-driven regulatory requirements for skills.

A policy is a YAML file that declares what a skill must satisfy to be
considered conformant. The framework ships an enforcement engine; the
organization ships the policy data.

Architecture:

  Policy              the data model — one parsed YAML file
  PolicyLoadError     structured load failure with a FrameworkError payload
  load_policy         read a YAML file into a Policy
  merge_policies      union multiple policies with deny-wins semantics
  PolicyEngine        validate a skill against a (merged) policy
  PolicyResult        per-requirement pass/fail with summary

The bbsctl policy CLI wraps these for `bbsctl policy {list,show,validate,lint}`.
A PolicyValidator wraps PolicyEngine to fit the existing validator chain.

See: docs/policy.md (this doc) for the schema and reference examples.
"""

from .base import (
    ApprovalRequirements,
    AuditRequirements,
    ComplianceMapping,
    CostRequirements,
    EvalRequirements,
    ForbiddenCommand,
    OwnershipRequirements,
    PermissionsRequirements,
    Policy,
    PolicyMetadata,
    PolicyResult,
    PolicyRequirement,
    RequiredArtifacts,
    RequirementCheck,
)
from .engine import PolicyEngine
from .loader import PolicyLoadError, load_policy, load_policy_from_dict
from .merger import merge_policies

__all__ = [
    "ApprovalRequirements",
    "AuditRequirements",
    "ComplianceMapping",
    "CostRequirements",
    "EvalRequirements",
    "ForbiddenCommand",
    "OwnershipRequirements",
    "PermissionsRequirements",
    "Policy",
    "PolicyEngine",
    "PolicyLoadError",
    "PolicyMetadata",
    "PolicyRequirement",
    "PolicyResult",
    "RequiredArtifacts",
    "RequirementCheck",
    "load_policy",
    "load_policy_from_dict",
    "merge_policies",
]
