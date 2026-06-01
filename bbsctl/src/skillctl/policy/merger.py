"""Merge multiple policies into one effective policy.

Multiple policies can apply to a single skill (HIPAA + internal-tier-1, for
example). The merge is **deny-wins**:

  - Required files / directories: union.
  - Required ownership fields: union.
  - last_reviewed_max_age_days: minimum of declared values (tighter wins).
  - Required eval suites: union.
  - judge_must_be_llm: any True → True.
  - injection_corpus_pinned / snapshots_required: any True → True.
  - Permissions require_default_deny: union of groups.
  - Forbidden commands: union (deduplicated by pattern).
  - Audit retention: max of declared values (longer wins).
  - Audit tamper_evident: any True → True.
  - Audit fail_mode: strictest wins (closed > degraded > open).
  - Required approvers: max count per role across policies.
  - Cost limits: minimum (tighter wins).
  - Compliance frameworks: union.
  - Custom validators: union.

The merged policy carries a synthetic metadata block listing the source
policy names so audit reports can attribute each requirement.
"""

from __future__ import annotations

from .base import (
    ApprovalRequirements,
    ApproverRole,
    AuditRequirements,
    ComplianceMapping,
    CostRequirements,
    EvalRequirements,
    ForbiddenCommand,
    ModelUpgradePolicy,
    OwnershipRequirements,
    PermissionsRequirements,
    Policy,
    PolicyMetadata,
    RequiredArtifacts,
)

_FAIL_MODE_RANK = {
    "fail-open": 0,
    "fail-degraded": 1,
    "fail-closed": 2,
    "": -1,
}


def merge_policies(*policies: Policy) -> Policy:
    """Merge policies with deny-wins semantics.

    Returns a single Policy. With zero inputs returns an empty default Policy.
    With one input returns it unchanged.
    """
    if not policies:
        return Policy(metadata=PolicyMetadata(name="empty", version="0.0.0"))
    if len(policies) == 1:
        return policies[0]

    name_parts = [p.metadata.name for p in policies if p.metadata.name]
    merged_name = "+".join(name_parts) if name_parts else "merged"

    return Policy(
        metadata=PolicyMetadata(
            name=merged_name,
            version="merged",
            description=(
                "Synthetic merged policy from: " + ", ".join(name_parts)
            ),
        ),
        applies_to_strictness=_union_tuples(
            *(p.applies_to_strictness for p in policies)
        ),
        required_artifacts=_merge_required_artifacts(policies),
        ownership=_merge_ownership(policies),
        eval=_merge_eval(policies),
        permissions=_merge_permissions(policies),
        audit=_merge_audit(policies),
        approval=_merge_approval(policies),
        cost=_merge_cost(policies),
        compliance_frameworks=_merge_compliance(policies),
        custom_validators=_union_tuples(
            *(p.custom_validators for p in policies)
        ),
    )


# ── per-section mergers ─────────────────────────────────────────────────────


def _merge_required_artifacts(policies):
    return RequiredArtifacts(
        files=_union_tuples(*(p.required_artifacts.files for p in policies)),
        directories=_union_tuples(
            *(p.required_artifacts.directories for p in policies)
        ),
        references_must_exist=any(
            p.required_artifacts.references_must_exist for p in policies
        ),
    )


def _merge_ownership(policies):
    return OwnershipRequirements(
        required_fields=_union_tuples(
            *(p.ownership.required_fields for p in policies)
        ),
        last_reviewed_max_age_days=_min_optional(
            *(p.ownership.last_reviewed_max_age_days for p in policies)
        ),
        require_security_reviewer=any(
            p.ownership.require_security_reviewer for p in policies
        ),
    )


def _merge_eval(policies):
    upgrades = [p.eval.model_upgrade for p in policies if p.eval.model_upgrade]
    merged_upgrade = None
    if upgrades:
        merged_upgrade = ModelUpgradePolicy(
            re_eval_required=any(u.re_eval_required for u in upgrades),
            block_on_regression=any(u.block_on_regression for u in upgrades),
            regression_threshold=min(u.regression_threshold for u in upgrades),
        )
    return EvalRequirements(
        min_score=_max_optional(*(p.eval.min_score for p in policies)),
        min_threshold=_max_optional(*(p.eval.min_threshold for p in policies)),
        required_suites=_union_tuples(*(p.eval.required_suites for p in policies)),
        injection_corpus_pinned=any(
            p.eval.injection_corpus_pinned for p in policies
        ),
        snapshots_required=any(p.eval.snapshots_required for p in policies),
        judge_must_be_llm=any(p.eval.judge_must_be_llm for p in policies),
        model_upgrade=merged_upgrade,
    )


def _merge_permissions(policies):
    # Dedupe forbidden_commands by pattern.
    seen: set[str] = set()
    forbidden: list[ForbiddenCommand] = []
    for p in policies:
        for f in p.permissions.forbidden_commands:
            if f.pattern not in seen:
                forbidden.append(f)
                seen.add(f.pattern)
    return PermissionsRequirements(
        require_default_deny=_union_tuples(
            *(p.permissions.require_default_deny for p in policies)
        ),
        forbidden_commands=tuple(forbidden),
        require_namespace_isolation=any(
            p.permissions.require_namespace_isolation for p in policies
        ),
        redact_required_patterns=_union_tuples(
            *(p.permissions.redact_required_patterns for p in policies)
        ),
    )


def _merge_audit(policies):
    fail_modes = [p.audit.fail_mode for p in policies if p.audit.fail_mode]
    strictest = ""
    if fail_modes:
        strictest = max(
            fail_modes, key=lambda m: _FAIL_MODE_RANK.get(m, -1)
        )
    return AuditRequirements(
        retention_days=_max_optional(
            *(p.audit.retention_days for p in policies)
        ),
        tamper_evident=any(p.audit.tamper_evident for p in policies),
        fail_mode=strictest,
        required_fields=_union_tuples(
            *(p.audit.required_fields for p in policies)
        ),
    )


def _merge_approval(policies):
    # Sum required counts per role across policies (tightest wins via max).
    role_max: dict[str, int] = {}
    for p in policies:
        for a in p.approval.required_approvers:
            role_max[a.role] = max(role_max.get(a.role, 0), a.count)
    approvers = tuple(
        ApproverRole(role=role, count=count)
        for role, count in sorted(role_max.items())
    )
    return ApprovalRequirements(
        required_approvers=approvers,
        sign_off_yaml_required=any(
            p.approval.sign_off_yaml_required for p in policies
        ),
    )


def _merge_cost(policies):
    return CostRequirements(
        max_tokens_per_run=_min_optional(
            *(p.cost.max_tokens_per_run for p in policies)
        ),
        max_cost_usd_per_month=_min_optional(
            *(p.cost.max_cost_usd_per_month for p in policies)
        ),
    )


def _merge_compliance(policies):
    seen: dict[str, set[str]] = {}
    for p in policies:
        for f in p.compliance_frameworks:
            seen.setdefault(f.id, set()).update(f.controls)
    return tuple(
        ComplianceMapping(id=fid, controls=tuple(sorted(controls)))
        for fid, controls in sorted(seen.items())
    )


# ── helpers ─────────────────────────────────────────────────────────────────


def _union_tuples(*tuples: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tuples:
        for item in t:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return tuple(out)


def _min_optional(*values):
    """Min of non-None values; None if all are None."""
    real = [v for v in values if v is not None]
    return min(real) if real else None


def _max_optional(*values):
    """Max of non-None values; None if all are None."""
    real = [v for v in values if v is not None]
    return max(real) if real else None


__all__ = ["merge_policies"]
