"""Load and parse a policy YAML file into a `Policy` dataclass."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError

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
    RiskControl,
)


class PolicyLoadError(Exception):
    """Raised when a policy file is unparseable or missing required fields.

    Carries a FrameworkError for the caller to emit.
    """

    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


def load_policy(path: Path) -> Policy:
    """Load a policy from a YAML file.

    Raises PolicyLoadError on malformed YAML, non-mapping top-level, or
    missing required metadata fields.
    """
    if not path.exists():
        raise PolicyLoadError(
            FrameworkError(
                summary=f"policy file not found: {path}",
                fix=(
                    "Check the path. List bundled policies with `bbsctl policy list`."
                ),
            )
        )

    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path)
    except Exception as exc:
        raise PolicyLoadError(
            FrameworkError(
                summary=f"policy YAML parse error: {path}",
                detail=str(exc),
                fix="Fix the YAML syntax. See docs/policy.md for the schema.",
                docs="../docs/policy.md",
            )
        ) from exc

    if not isinstance(raw, dict):
        raise PolicyLoadError(
            FrameworkError(
                summary=f"policy {path.name}: top-level must be a mapping",
                fix=(
                    "Start the file with `schema_version: bulbasaur/v1` and "
                    "a `policy:` block."
                ),
            )
        )

    return load_policy_from_dict(raw, source=path)


def load_policy_from_dict(raw: dict[str, Any], *, source: Path | None = None) -> Policy:
    """Parse a raw policy dict into a Policy.

    Used internally by load_policy + by tests that want to construct
    in-memory policies without a file.
    """
    source_label = str(source) if source else "<inline>"
    policy_block = raw.get("policy", {})
    if not isinstance(policy_block, dict):
        raise PolicyLoadError(
            FrameworkError(
                summary=f"policy {source_label}: `policy:` block must be a mapping",
                fix="Wrap the policy fields under a top-level `policy:` key.",
            )
        )

    metadata = _parse_metadata(policy_block, source_label=source_label)
    applies = _parse_string_tuple(policy_block.get("applies_to_strictness"))
    required_artifacts = _parse_required_artifacts(policy_block.get("required_artifacts"))
    ownership = _parse_ownership(policy_block.get("ownership"))
    eval_req = _parse_eval(policy_block.get("eval"))
    permissions = _parse_permissions(policy_block.get("permissions"))
    audit = _parse_audit(policy_block.get("audit"))
    approval = _parse_approval(policy_block.get("approval"))
    cost = _parse_cost(policy_block.get("cost"))
    compliance = _parse_compliance(policy_block.get("compliance_frameworks"))
    custom = _parse_string_tuple(policy_block.get("custom_validators"))
    risk_controls = _parse_risk_controls(policy_block.get("risk_controls"))
    require_risk_profile = bool(policy_block.get("require_risk_profile", False))
    require_complete_risk_profile = bool(
        policy_block.get("require_complete_risk_profile", False)
    )

    return Policy(
        metadata=metadata,
        applies_to_strictness=applies,
        required_artifacts=required_artifacts,
        ownership=ownership,
        eval=eval_req,
        permissions=permissions,
        audit=audit,
        approval=approval,
        cost=cost,
        compliance_frameworks=compliance,
        custom_validators=custom,
        risk_controls=risk_controls,
        require_risk_profile=require_risk_profile,
        require_complete_risk_profile=require_complete_risk_profile,
    )


def _parse_risk_controls(block: Any) -> tuple[RiskControl, ...]:
    """Parse risk_controls: list of per-level required-controls blocks."""
    if not isinstance(block, list):
        return ()
    out: list[RiskControl] = []
    for entry in block:
        if not isinstance(entry, dict):
            continue
        level = str(entry.get("level") or "").lower()
        if level not in {"low", "medium", "high", "critical"}:
            continue
        forbidden = _parse_string_tuple(entry.get("forbidden_data_classifications"))
        out.append(
            RiskControl(
                level=level,
                require_sandbox=bool(entry.get("require_sandbox", False)),
                require_signature=bool(entry.get("require_signature", False)),
                require_human_approval=bool(entry.get("require_human_approval", False)),
                require_security_reviewer=bool(
                    entry.get("require_security_reviewer", False)
                ),
                require_injection_corpus=bool(
                    entry.get("require_injection_corpus", False)
                ),
                max_side_effects=str(entry.get("max_side_effects") or ""),
                forbidden_data_classifications=forbidden,
            )
        )
    return tuple(out)


# ── per-section parsers ─────────────────────────────────────────────────────


def _parse_metadata(block: dict, *, source_label: str) -> PolicyMetadata:
    name = str(block.get("name") or "")
    version = str(block.get("version") or "")
    if not name:
        raise PolicyLoadError(
            FrameworkError(
                summary=f"policy {source_label}: missing required field `name`",
                fix="Add `name: <policy-id>` (e.g. `hipaa-baseline`) under `policy:`.",
            )
        )
    if not version:
        raise PolicyLoadError(
            FrameworkError(
                summary=f"policy {source_label}: missing required field `version`",
                fix="Add `version: <semver>` (e.g. `1.0.0`) under `policy:`.",
            )
        )
    return PolicyMetadata(
        name=name,
        version=version,
        effective_date=_parse_date(block.get("effective_date")),
        expiry_date=_parse_date(block.get("expiry_date")),
        authority=str(block.get("authority") or ""),
        description=str(block.get("description") or ""),
    )


def _parse_required_artifacts(block: Any) -> RequiredArtifacts:
    if not isinstance(block, dict):
        return RequiredArtifacts()
    return RequiredArtifacts(
        files=_parse_string_tuple(block.get("files")),
        directories=_parse_string_tuple(block.get("directories")),
        references_must_exist=bool(block.get("references_must_exist", False)),
    )


def _parse_ownership(block: Any) -> OwnershipRequirements:
    if not isinstance(block, dict):
        return OwnershipRequirements()
    return OwnershipRequirements(
        required_fields=_parse_string_tuple(block.get("required_fields")),
        last_reviewed_max_age_days=_parse_optional_int(block.get("last_reviewed_max_age_days")),
        require_security_reviewer=bool(block.get("require_security_reviewer", False)),
    )


def _parse_eval(block: Any) -> EvalRequirements:
    if not isinstance(block, dict):
        return EvalRequirements()
    upgrade_block = block.get("model_upgrade")
    upgrade = None
    if isinstance(upgrade_block, dict):
        upgrade = ModelUpgradePolicy(
            re_eval_required=bool(upgrade_block.get("re_eval_required", False)),
            block_on_regression=bool(upgrade_block.get("block_on_regression", False)),
            regression_threshold=_parse_float(
                upgrade_block.get("regression_threshold"), default=0.0
            ),
        )
    return EvalRequirements(
        min_score=_parse_optional_float(block.get("min_score")),
        min_threshold=_parse_optional_float(block.get("min_threshold")),
        required_suites=_parse_string_tuple(block.get("required_suites")),
        injection_corpus_pinned=bool(block.get("injection_corpus_pinned", False)),
        snapshots_required=bool(block.get("snapshots_required", False)),
        judge_must_be_llm=bool(block.get("judge_must_be_llm", False)),
        model_upgrade=upgrade,
    )


def _parse_permissions(block: Any) -> PermissionsRequirements:
    if not isinstance(block, dict):
        return PermissionsRequirements()
    forbidden_raw = block.get("forbidden_commands") or []
    forbidden: list[ForbiddenCommand] = []
    if isinstance(forbidden_raw, list):
        for entry in forbidden_raw:
            if isinstance(entry, dict):
                pattern = str(entry.get("pattern") or "")
                if pattern:
                    forbidden.append(
                        ForbiddenCommand(
                            pattern=pattern,
                            reason=str(entry.get("reason") or ""),
                        )
                    )
            elif isinstance(entry, str):
                forbidden.append(ForbiddenCommand(pattern=entry))
    return PermissionsRequirements(
        require_default_deny=_parse_string_tuple(block.get("require_default_deny")),
        forbidden_commands=tuple(forbidden),
        require_namespace_isolation=bool(block.get("require_namespace_isolation", False)),
        redact_required_patterns=_parse_string_tuple(block.get("redact_required_patterns")),
    )


def _parse_audit(block: Any) -> AuditRequirements:
    if not isinstance(block, dict):
        return AuditRequirements()
    return AuditRequirements(
        retention_days=_parse_optional_int(block.get("retention_days")),
        tamper_evident=bool(block.get("tamper_evident", False)),
        fail_mode=str(block.get("fail_mode") or ""),
        required_fields=_parse_string_tuple(block.get("required_fields")),
    )


def _parse_approval(block: Any) -> ApprovalRequirements:
    if not isinstance(block, dict):
        return ApprovalRequirements()
    approvers_raw = block.get("required_approvers") or []
    approvers: list[ApproverRole] = []
    if isinstance(approvers_raw, list):
        for entry in approvers_raw:
            if isinstance(entry, dict):
                role = str(entry.get("role") or "")
                if role:
                    approvers.append(
                        ApproverRole(
                            role=role,
                            count=_parse_optional_int(entry.get("count")) or 1,
                        )
                    )
    return ApprovalRequirements(
        required_approvers=tuple(approvers),
        sign_off_yaml_required=bool(block.get("sign_off_yaml_required", False)),
    )


def _parse_cost(block: Any) -> CostRequirements:
    if not isinstance(block, dict):
        return CostRequirements()
    return CostRequirements(
        max_tokens_per_run=_parse_optional_int(block.get("max_tokens_per_run")),
        max_cost_usd_per_month=_parse_optional_float(block.get("max_cost_usd_per_month")),
    )


def _parse_compliance(block: Any) -> tuple[ComplianceMapping, ...]:
    if not isinstance(block, list):
        return ()
    out: list[ComplianceMapping] = []
    for entry in block:
        if isinstance(entry, dict):
            framework_id = str(entry.get("id") or "")
            if framework_id:
                out.append(
                    ComplianceMapping(
                        id=framework_id,
                        controls=_parse_string_tuple(entry.get("controls")),
                    )
                )
        elif isinstance(entry, str):
            out.append(ComplianceMapping(id=entry))
    return tuple(out)


# ── primitives ──────────────────────────────────────────────────────────────


def _parse_string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(v) for v in value if v is not None)
    if isinstance(value, str):
        return (value,)
    return ()


def _parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


__all__ = ["PolicyLoadError", "load_policy", "load_policy_from_dict"]
