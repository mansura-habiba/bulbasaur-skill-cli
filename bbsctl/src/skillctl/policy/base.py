"""Policy data model.

The schema mirrors the design in docs/policy.md. Each section of the policy
maps to one of the existing artifact validators so the engine becomes a
data-driven dispatcher rather than a new validation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


# ── policy metadata ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PolicyMetadata:
    """Header fields identifying the policy."""

    name: str
    version: str
    effective_date: date | None = None
    expiry_date: date | None = None
    authority: str = ""
    description: str = ""

    def is_active(self, *, today: date | None = None) -> bool:
        """True if the policy's window covers `today` (default: today)."""
        ref = today or date.today()
        if self.effective_date and ref < self.effective_date:
            return False
        if self.expiry_date and ref > self.expiry_date:
            return False
        return True


# ── per-section requirement dataclasses ─────────────────────────────────────


@dataclass(frozen=True)
class RequiredArtifacts:
    """Files and directories that must exist beside SKILL.md."""

    files: tuple[str, ...] = ()
    directories: tuple[str, ...] = ()
    references_must_exist: bool = False


@dataclass(frozen=True)
class OwnershipRequirements:
    """Subset of ownership.yaml fields required by this policy."""

    required_fields: tuple[str, ...] = ()
    last_reviewed_max_age_days: int | None = None
    require_security_reviewer: bool = False


@dataclass(frozen=True)
class ModelUpgradePolicy:
    """How a model upgrade is gated."""

    re_eval_required: bool = False
    block_on_regression: bool = False
    regression_threshold: float = 0.0


@dataclass(frozen=True)
class EvalRequirements:
    """Eval-corpus and report requirements."""

    min_score: float | None = None
    min_threshold: float | None = None
    required_suites: tuple[str, ...] = ()
    injection_corpus_pinned: bool = False
    snapshots_required: bool = False
    judge_must_be_llm: bool = False
    model_upgrade: ModelUpgradePolicy | None = None


@dataclass(frozen=True)
class ForbiddenCommand:
    """One forbidden command pattern + the reason it's forbidden."""

    pattern: str
    reason: str = ""


@dataclass(frozen=True)
class PermissionsRequirements:
    """Requirements applied to permissions.yaml."""

    require_default_deny: tuple[str, ...] = ()
    forbidden_commands: tuple[ForbiddenCommand, ...] = ()
    require_namespace_isolation: bool = False
    redact_required_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditRequirements:
    """Runtime audit-stream requirements."""

    retention_days: int | None = None
    tamper_evident: bool = False
    fail_mode: str = ""        # fail-open | fail-degraded | fail-closed
    required_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApproverRole:
    role: str
    count: int = 1


@dataclass(frozen=True)
class ApprovalRequirements:
    required_approvers: tuple[ApproverRole, ...] = ()
    sign_off_yaml_required: bool = False


@dataclass(frozen=True)
class CostRequirements:
    max_tokens_per_run: int | None = None
    max_cost_usd_per_month: float | None = None


@dataclass(frozen=True)
class ComplianceMapping:
    """Declarative regulatory framework mapping. Documentation, not enforcement."""

    id: str
    controls: tuple[str, ...] = ()


@dataclass(frozen=True)
class Policy:
    """A complete parsed policy file."""

    metadata: PolicyMetadata
    applies_to_strictness: tuple[str, ...] = ()
    required_artifacts: RequiredArtifacts = field(default_factory=RequiredArtifacts)
    ownership: OwnershipRequirements = field(default_factory=OwnershipRequirements)
    eval: EvalRequirements = field(default_factory=EvalRequirements)
    permissions: PermissionsRequirements = field(default_factory=PermissionsRequirements)
    audit: AuditRequirements = field(default_factory=AuditRequirements)
    approval: ApprovalRequirements = field(default_factory=ApprovalRequirements)
    cost: CostRequirements = field(default_factory=CostRequirements)
    compliance_frameworks: tuple[ComplianceMapping, ...] = ()
    custom_validators: tuple[str, ...] = ()


# ── requirement evaluation result ───────────────────────────────────────────


class CheckOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"            # not applicable (e.g. retention check at non-regulated)
    UNKNOWN = "unknown"      # framework cannot evaluate (e.g. cost limit needs runtime)


@dataclass
class RequirementCheck:
    """Result of one requirement evaluation."""

    section: str             # `required_artifacts`, `ownership`, `eval`, etc.
    requirement: str         # human-readable summary
    outcome: CheckOutcome
    detail: str = ""
    fix: str = ""


@dataclass
class PolicyResult:
    """Aggregated result of a PolicyEngine.validate() call."""

    policy_name: str
    policy_version: str
    skill_dir: str
    checks: list[RequirementCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.outcome != CheckOutcome.FAIL for c in self.checks)

    @property
    def failures(self) -> list[RequirementCheck]:
        return [c for c in self.checks if c.outcome == CheckOutcome.FAIL]

    @property
    def warnings(self) -> list[RequirementCheck]:
        return [c for c in self.checks if c.outcome == CheckOutcome.UNKNOWN]

    @property
    def total_checks(self) -> int:
        return len(self.checks)

    @property
    def passed_checks(self) -> int:
        return sum(1 for c in self.checks if c.outcome == CheckOutcome.PASS)


# ── requirement marker (for catalog discovery) ──────────────────────────────


@dataclass(frozen=True)
class PolicyRequirement:
    """Marker mapping a policy section to the validator that enforces it.

    Used by `bbsctl policy show` and the policy lint to surface which parts
    of a policy are honoured today vs marked as forward-compat.
    """

    section: str
    description: str
    enforced: bool = True


__all__ = [
    "ApprovalRequirements",
    "ApproverRole",
    "AuditRequirements",
    "CheckOutcome",
    "ComplianceMapping",
    "CostRequirements",
    "EvalRequirements",
    "ForbiddenCommand",
    "ModelUpgradePolicy",
    "OwnershipRequirements",
    "PermissionsRequirements",
    "Policy",
    "PolicyMetadata",
    "PolicyRequirement",
    "PolicyResult",
    "RequiredArtifacts",
    "RequirementCheck",
]
