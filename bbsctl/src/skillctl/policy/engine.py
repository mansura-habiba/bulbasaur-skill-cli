"""PolicyEngine — validate a skill against a (merged) policy.

The engine inspects existing skill artifacts (SKILL.md, skill.yaml,
permissions.yaml, ownership.yaml, evals/) and emits a `RequirementCheck` per
declared policy requirement. The engine does not duplicate the existing
validators; it builds on their loaders so the policy layer is a data-driven
dispatcher rather than parallel code.

Outcomes per check:

  PASS    requirement satisfied
  FAIL    requirement violated — policy blocks
  SKIP    requirement not applicable at this strictness / scope
  UNKNOWN requirement declared but framework lacks the runtime data to
          evaluate (cost limits, audit-stream presence, etc.). Surfaced as a
          warning rather than a failure so the policy author can see what's
          tracked vs aspirational.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from skillctl.ownership.loader import OwnershipLoadError, load_ownership
from skillctl.permissions.base import DecisionType, RuleGroup
from skillctl.permissions.loader import PermissionsLoadError, load_permissions
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness

from .base import (
    CheckOutcome,
    Policy,
    PolicyResult,
    RequirementCheck,
)


class PolicyEngine:
    """Run policy requirements against a skill directory."""

    def __init__(self, policy: Policy) -> None:
        self._policy = policy

    def validate(self, skill_dir: Path, strictness: Strictness) -> PolicyResult:
        result = PolicyResult(
            policy_name=self._policy.metadata.name,
            policy_version=self._policy.metadata.version,
            skill_dir=str(skill_dir),
        )

        # Policy-window check: if the policy is outside its effective window,
        # surface as FAIL up front.
        if not self._policy.metadata.is_active():
            result.checks.append(
                RequirementCheck(
                    section="metadata",
                    requirement="policy effective window",
                    outcome=CheckOutcome.FAIL,
                    detail=(
                        f"policy {self._policy.metadata.name}@{self._policy.metadata.version} "
                        f"is outside its effective window "
                        f"(effective_date={self._policy.metadata.effective_date}, "
                        f"expiry_date={self._policy.metadata.expiry_date})"
                    ),
                    fix=(
                        "Update the policy's effective_date / expiry_date, or "
                        "switch to a currently-effective policy."
                    ),
                )
            )
            return result

        # Strictness applicability — if declared and not in the list, SKIP.
        if (
            self._policy.applies_to_strictness
            and strictness.value not in self._policy.applies_to_strictness
        ):
            result.checks.append(
                RequirementCheck(
                    section="metadata",
                    requirement="applies_to_strictness",
                    outcome=CheckOutcome.SKIP,
                    detail=(
                        f"policy applies to {list(self._policy.applies_to_strictness)} "
                        f"but skill is at strictness `{strictness.value}`"
                    ),
                )
            )
            return result

        # Run each section.
        self._check_required_artifacts(skill_dir, result)
        self._check_ownership(skill_dir, strictness, result)
        self._check_eval(skill_dir, result)
        self._check_permissions(skill_dir, result)
        self._check_audit(result)
        self._check_approval(skill_dir, result)
        self._check_cost(result)

        return result

    # ── required_artifacts ────────────────────────────────────────────

    def _check_required_artifacts(self, skill_dir: Path, result: PolicyResult) -> None:
        req = self._policy.required_artifacts
        for relative in req.files:
            path = skill_dir / relative
            result.checks.append(
                RequirementCheck(
                    section="required_artifacts.files",
                    requirement=f"file present: {relative}",
                    outcome=CheckOutcome.PASS if path.is_file() else CheckOutcome.FAIL,
                    detail=f"path: {path}",
                    fix=f"Create the file at {relative}." if not path.is_file() else "",
                )
            )
        for relative in req.directories:
            path = skill_dir / relative
            result.checks.append(
                RequirementCheck(
                    section="required_artifacts.directories",
                    requirement=f"directory present: {relative}",
                    outcome=CheckOutcome.PASS if path.is_dir() else CheckOutcome.FAIL,
                    detail=f"path: {path}",
                    fix=(
                        f"Create the directory at {relative}."
                        if not path.is_dir()
                        else ""
                    ),
                )
            )

    # ── ownership ─────────────────────────────────────────────────────

    def _check_ownership(
        self, skill_dir: Path, strictness: Strictness, result: PolicyResult
    ) -> None:
        req = self._policy.ownership
        if not (
            req.required_fields
            or req.last_reviewed_max_age_days is not None
            or req.require_security_reviewer
        ):
            return

        try:
            ownership = load_ownership(skill_dir)
        except OwnershipLoadError as exc:
            result.checks.append(
                RequirementCheck(
                    section="ownership",
                    requirement="ownership.yaml loadable",
                    outcome=CheckOutcome.FAIL,
                    detail=exc.framework_error.summary,
                    fix=exc.framework_error.fix or "",
                )
            )
            return

        if ownership is None:
            # Fall back to skill.yaml embedded OwnershipRef.
            try:
                overlay = load_skill_yaml(skill_dir)
            except SkillYamlError:
                overlay = None
            if overlay is None or not overlay.has_ownership:
                result.checks.append(
                    RequirementCheck(
                        section="ownership",
                        requirement="ownership artifact present",
                        outcome=CheckOutcome.FAIL,
                        detail="neither ownership.yaml nor skill.yaml `ownership:` block found",
                        fix="Create ownership.yaml. See docs/strictness-levels.md.",
                    )
                )
                return
            # OwnershipRef is too shallow for full org-tier checks; surface UNKNOWN.
            result.checks.append(
                RequirementCheck(
                    section="ownership",
                    requirement="full ownership.yaml present",
                    outcome=CheckOutcome.UNKNOWN,
                    detail="only skill.yaml `ownership:` stub found",
                    fix="Promote to a standalone ownership.yaml for org-tier checks.",
                )
            )
            return

        # Check required fields exist on the loaded ownership.
        for field_name in req.required_fields:
            if not _ownership_has(ownership, field_name):
                result.checks.append(
                    RequirementCheck(
                        section="ownership.required_fields",
                        requirement=f"ownership.{field_name} set",
                        outcome=CheckOutcome.FAIL,
                        fix=f"Add `{field_name}:` to ownership.yaml.",
                    )
                )
            else:
                result.checks.append(
                    RequirementCheck(
                        section="ownership.required_fields",
                        requirement=f"ownership.{field_name} set",
                        outcome=CheckOutcome.PASS,
                    )
                )

        if req.last_reviewed_max_age_days is not None:
            if ownership.last_reviewed is None:
                result.checks.append(
                    RequirementCheck(
                        section="ownership.last_reviewed",
                        requirement=(
                            f"last_reviewed within {req.last_reviewed_max_age_days} days"
                        ),
                        outcome=CheckOutcome.FAIL,
                        detail="ownership.yaml has no last_reviewed",
                        fix="Add `last_reviewed: YYYY-MM-DD` and run an ownership review.",
                    )
                )
            else:
                age = date.today() - ownership.last_reviewed
                if age > timedelta(days=req.last_reviewed_max_age_days):
                    result.checks.append(
                        RequirementCheck(
                            section="ownership.last_reviewed",
                            requirement=(
                                f"last_reviewed within {req.last_reviewed_max_age_days} days"
                            ),
                            outcome=CheckOutcome.FAIL,
                            detail=f"last_reviewed is {age.days} days old",
                            fix=(
                                "Run an ownership review and update `last_reviewed:` "
                                "to today's date."
                            ),
                        )
                    )
                else:
                    result.checks.append(
                        RequirementCheck(
                            section="ownership.last_reviewed",
                            requirement=(
                                f"last_reviewed within {req.last_reviewed_max_age_days} days"
                            ),
                            outcome=CheckOutcome.PASS,
                            detail=f"reviewed {age.days} days ago",
                        )
                    )

        if req.require_security_reviewer:
            # Heuristic: look for a `security` role in escalation contacts
            # or a security_reviewer field on ownership.
            has_sec = any(
                "security" in (e.role if hasattr(e, "role") else "") .lower()
                for e in ownership.escalation
            ) or any(
                "security" in field_name.lower()
                for field_name in req.required_fields
                if _ownership_has(ownership, field_name)
            )
            result.checks.append(
                RequirementCheck(
                    section="ownership.security_reviewer",
                    requirement="security reviewer declared",
                    outcome=CheckOutcome.PASS if has_sec else CheckOutcome.UNKNOWN,
                    detail=(
                        "no explicit `security_reviewer` field; relying on escalation roles"
                    ),
                    fix=(
                        "Add a `security_reviewer:` field to ownership.yaml, or "
                        "include a security role in the escalation chain."
                    ),
                )
            )

    # ── eval ──────────────────────────────────────────────────────────

    def _check_eval(self, skill_dir: Path, result: PolicyResult) -> None:
        req = self._policy.eval
        if not any(
            (
                req.min_score is not None,
                req.min_threshold is not None,
                req.required_suites,
                req.injection_corpus_pinned,
                req.snapshots_required,
                req.judge_must_be_llm,
                req.model_upgrade is not None,
            )
        ):
            return

        evals_dir = skill_dir / "evals"

        for suite_name in req.required_suites:
            path = evals_dir / f"{suite_name}.json"
            if path.is_file():
                # Best-effort: check it has at least one case.
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    n = len(data.get("evals", []) or [])
                except Exception:
                    n = 0
                result.checks.append(
                    RequirementCheck(
                        section="eval.required_suites",
                        requirement=f"suite `{suite_name}` present with ≥1 case",
                        outcome=CheckOutcome.PASS if n >= 1 else CheckOutcome.FAIL,
                        detail=f"cases: {n}",
                        fix=(
                            f"Add at least one case to {path}." if n < 1 else ""
                        ),
                    )
                )
            else:
                result.checks.append(
                    RequirementCheck(
                        section="eval.required_suites",
                        requirement=f"suite `{suite_name}` present",
                        outcome=CheckOutcome.FAIL,
                        detail=f"missing: {path}",
                        fix=f"Create {path} (see docs/evaluation.md).",
                    )
                )

        if req.snapshots_required:
            snap_dir = evals_dir / "snapshots"
            has_snap = snap_dir.is_dir() and any(snap_dir.iterdir())
            result.checks.append(
                RequirementCheck(
                    section="eval.snapshots_required",
                    requirement="evals/snapshots/ contains baselines",
                    outcome=CheckOutcome.PASS if has_snap else CheckOutcome.FAIL,
                    fix=(
                        "Run `bbsctl eval --snapshot <suite>` to write baselines."
                        if not has_snap
                        else ""
                    ),
                )
            )

        if req.injection_corpus_pinned:
            # Pinned == hash recorded in skill.yaml extra fields. We surface
            # UNKNOWN if absent — the wiring lands when skill.yaml gains the
            # `pinned_corpora` field.
            try:
                overlay = load_skill_yaml(skill_dir)
            except SkillYamlError:
                overlay = None
            pinned = overlay.extra.get("pinned_corpora") if overlay else None
            if isinstance(pinned, dict) and "injection" in pinned:
                result.checks.append(
                    RequirementCheck(
                        section="eval.injection_corpus_pinned",
                        requirement="injection corpus hash pinned in skill.yaml",
                        outcome=CheckOutcome.PASS,
                        detail=f"hash: {str(pinned['injection'])[:16]}...",
                    )
                )
            else:
                result.checks.append(
                    RequirementCheck(
                        section="eval.injection_corpus_pinned",
                        requirement="injection corpus hash pinned in skill.yaml",
                        outcome=CheckOutcome.FAIL,
                        fix=(
                            "Add `pinned_corpora: {injection: <sha256>}` to skill.yaml "
                            "and pin to the current injection corpus content."
                        ),
                    )
                )

        if req.judge_must_be_llm:
            # Read evals/eval.config.yaml if present.
            from skillctl.eval.reproducibility import EvalConfigError, load_eval_config

            try:
                eval_cfg = load_eval_config(skill_dir)
            except EvalConfigError:
                eval_cfg = None
            judge = eval_cfg.judge if eval_cfg else ""
            result.checks.append(
                RequirementCheck(
                    section="eval.judge_must_be_llm",
                    requirement="judge configured as `llm`",
                    outcome=CheckOutcome.PASS if judge == "llm" else CheckOutcome.FAIL,
                    detail=f"resolved judge: {judge or '(default heuristic)'}",
                    fix=(
                        "Set `judge: llm` in evals/eval.config.yaml or via "
                        "BBSCTL_EVAL_JUDGE=llm."
                        if judge != "llm"
                        else ""
                    ),
                )
            )

        # min_score / min_threshold / model_upgrade depend on a recent eval
        # report; surface as UNKNOWN at validate-time (the publish gate
        # enforces them against the actual report).
        if req.min_score is not None:
            result.checks.append(
                RequirementCheck(
                    section="eval.min_score",
                    requirement=f"latest eval-report.score ≥ {req.min_score}",
                    outcome=CheckOutcome.UNKNOWN,
                    detail="enforced at publish-time against dist/eval-report.json",
                )
            )
        if req.min_threshold is not None:
            result.checks.append(
                RequirementCheck(
                    section="eval.min_threshold",
                    requirement=f"eval threshold ≥ {req.min_threshold}",
                    outcome=CheckOutcome.UNKNOWN,
                    detail="enforced at publish-time against dist/eval-report.json",
                )
            )
        if req.model_upgrade is not None:
            result.checks.append(
                RequirementCheck(
                    section="eval.model_upgrade",
                    requirement="model upgrade re-eval policy declared",
                    outcome=CheckOutcome.UNKNOWN,
                    detail=(
                        "block_on_regression="
                        f"{req.model_upgrade.block_on_regression}; "
                        "enforced by the publish gate during model upgrades"
                    ),
                )
            )

    # ── permissions ───────────────────────────────────────────────────

    def _check_permissions(self, skill_dir: Path, result: PolicyResult) -> None:
        req = self._policy.permissions
        if not any(
            (
                req.require_default_deny,
                req.forbidden_commands,
                req.require_namespace_isolation,
                req.redact_required_patterns,
            )
        ):
            return

        try:
            perms = load_permissions(skill_dir)
        except PermissionsLoadError as exc:
            result.checks.append(
                RequirementCheck(
                    section="permissions",
                    requirement="permissions.yaml loadable",
                    outcome=CheckOutcome.FAIL,
                    detail=exc.framework_error.summary,
                    fix=exc.framework_error.fix or "",
                )
            )
            return

        if perms is None:
            result.checks.append(
                RequirementCheck(
                    section="permissions",
                    requirement="permissions.yaml present",
                    outcome=CheckOutcome.FAIL,
                    fix="Create permissions.yaml. See docs/permissions.md.",
                )
            )
            return

        # require_default_deny per group
        for group_name in req.require_default_deny:
            try:
                group = RuleGroup(group_name)
            except ValueError:
                result.checks.append(
                    RequirementCheck(
                        section="permissions.require_default_deny",
                        requirement=f"unknown group `{group_name}`",
                        outcome=CheckOutcome.FAIL,
                        fix=(
                            f"Valid groups: {', '.join(g.value for g in RuleGroup)}."
                        ),
                    )
                )
                continue
            actual = perms.default_for(group)
            ok = actual == DecisionType.DENY
            result.checks.append(
                RequirementCheck(
                    section="permissions.require_default_deny",
                    requirement=f"{group_name}.default = deny",
                    outcome=CheckOutcome.PASS if ok else CheckOutcome.FAIL,
                    detail=f"actual: {actual.value}",
                    fix=(
                        f"Set `{group_name}.default: deny` in permissions.yaml."
                        if not ok
                        else ""
                    ),
                )
            )

        # forbidden_commands — every required-deny pattern must appear in
        # permissions.yaml deny list (or be subsumed by an existing pattern).
        existing_deny_patterns = {r.pattern for r in perms.commands_deny}
        for forbidden in req.forbidden_commands:
            covered = forbidden.pattern in existing_deny_patterns
            result.checks.append(
                RequirementCheck(
                    section="permissions.forbidden_commands",
                    requirement=f"deny rule covers `{forbidden.pattern}`",
                    outcome=CheckOutcome.PASS if covered else CheckOutcome.FAIL,
                    detail=forbidden.reason,
                    fix=(
                        f"Add to permissions.yaml commands.deny: "
                        f"{{pattern: {forbidden.pattern!r}, reason: {forbidden.reason!r}}}."
                        if not covered
                        else ""
                    ),
                )
            )

        if req.require_namespace_isolation:
            ok = bool(perms.namespaces_allow) or bool(perms.namespaces_deny)
            result.checks.append(
                RequirementCheck(
                    section="permissions.require_namespace_isolation",
                    requirement="namespaces allow or deny list declared",
                    outcome=CheckOutcome.PASS if ok else CheckOutcome.FAIL,
                    fix=(
                        "Add `namespaces.allow` or `namespaces.deny` in permissions.yaml."
                        if not ok
                        else ""
                    ),
                )
            )

        for pattern in req.redact_required_patterns:
            try:
                compiled = re.compile(pattern)
            except re.error:
                result.checks.append(
                    RequirementCheck(
                        section="permissions.redact_required_patterns",
                        requirement=f"redact pattern compiles: {pattern}",
                        outcome=CheckOutcome.FAIL,
                        fix="Fix the regex in the policy file.",
                    )
                )
                continue
            present = any(
                _patterns_equivalent(pattern, p) for p in perms.env_redact
            )
            result.checks.append(
                RequirementCheck(
                    section="permissions.redact_required_patterns",
                    requirement=f"redact pattern `{pattern}` declared",
                    outcome=CheckOutcome.PASS if present else CheckOutcome.FAIL,
                    fix=(
                        f"Add `{pattern}` to env.redact in permissions.yaml."
                        if not present
                        else ""
                    ),
                )
            )
            _ = compiled  # mute unused

    # ── audit / approval / cost ───────────────────────────────────────

    def _check_audit(self, result: PolicyResult) -> None:
        req = self._policy.audit
        for attr_name, requirement in (
            ("retention_days", "audit retention configured"),
            ("tamper_evident", "audit stream is tamper-evident"),
            ("fail_mode", "hook fail-mode set per policy"),
        ):
            value = getattr(req, attr_name)
            if value:
                result.checks.append(
                    RequirementCheck(
                        section=f"audit.{attr_name}",
                        requirement=requirement,
                        outcome=CheckOutcome.UNKNOWN,
                        detail=(
                            "audit-stream wiring is a runtime concern; "
                            "validated by the runtime hook bus when it lands"
                        ),
                    )
                )
        if req.required_fields:
            result.checks.append(
                RequirementCheck(
                    section="audit.required_fields",
                    requirement=f"audit JSONL includes: {', '.join(req.required_fields)}",
                    outcome=CheckOutcome.UNKNOWN,
                    detail="validated by the runtime hook schema",
                )
            )

    def _check_approval(self, skill_dir: Path, result: PolicyResult) -> None:
        req = self._policy.approval
        if req.sign_off_yaml_required:
            sign_off_dir = skill_dir / "approvals"
            has_signoff = sign_off_dir.is_dir() and any(sign_off_dir.glob("*.yaml"))
            result.checks.append(
                RequirementCheck(
                    section="approval.sign_off_yaml_required",
                    requirement="approvals/ contains sign-off yaml",
                    outcome=CheckOutcome.PASS if has_signoff else CheckOutcome.FAIL,
                    fix=(
                        "Create approvals/<policy>-<version>.yaml signed by the "
                        "required approvers."
                        if not has_signoff
                        else ""
                    ),
                )
            )
        if req.required_approvers:
            roles = ", ".join(f"{a.role}×{a.count}" for a in req.required_approvers)
            result.checks.append(
                RequirementCheck(
                    section="approval.required_approvers",
                    requirement=f"required approvers: {roles}",
                    outcome=CheckOutcome.UNKNOWN,
                    detail=(
                        "approver signatures verified by the publish gate, "
                        "not by validate"
                    ),
                )
            )

    def _check_cost(self, result: PolicyResult) -> None:
        req = self._policy.cost
        if req.max_tokens_per_run is not None:
            result.checks.append(
                RequirementCheck(
                    section="cost.max_tokens_per_run",
                    requirement=f"runs ≤ {req.max_tokens_per_run} tokens",
                    outcome=CheckOutcome.UNKNOWN,
                    detail="enforced by the runtime cost budget enforcer (Phase 4)",
                )
            )
        if req.max_cost_usd_per_month is not None:
            result.checks.append(
                RequirementCheck(
                    section="cost.max_cost_usd_per_month",
                    requirement=f"monthly spend ≤ ${req.max_cost_usd_per_month}",
                    outcome=CheckOutcome.UNKNOWN,
                    detail="enforced by the runtime cost budget enforcer (Phase 4)",
                )
            )


def _ownership_has(ownership, field_name: str) -> bool:
    """Return True if the named field is populated on the Ownership."""
    if not hasattr(ownership, field_name):
        return False
    value = getattr(ownership, field_name)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    return True


def _patterns_equivalent(a: str, b: str) -> bool:
    """Cheap pattern-equivalence: exact or substring containment."""
    return a == b or a in b or b in a


__all__ = ["PolicyEngine"]
