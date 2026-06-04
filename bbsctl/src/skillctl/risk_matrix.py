"""Risk × Strictness matrix — what each (strictness, risk_level) cell requires.

The two axes are orthogonal:

  Strictness  = author's consent (how much friction they've opted into)
  Risk level  = content (what the skill is allowed to do once it runs)

A formatting skill at `org` strictness is `low` risk. A deployment skill at
`org` strictness is `critical` risk. Different controls apply.

This module ships the framework's **default** matrix — 16 cells covering
every (local | team | org | regulated) × (low | medium | high | critical)
combination. Each cell declares:

  allowed                      can a skill of this (strictness, risk) ship at all?
  require_injection_corpus     evals/injection.json must exist
  require_human_approval       skill.yaml `risk.requires_human_approval: true`
  require_signed_bundle        bundle.sig must be a real signature, not placeholder
  require_sandbox              runtime sandbox enabled (Phase 4)
  require_security_reviewer    ownership.yaml lists a security reviewer
  max_side_effects             cap on the declared side_effects value

Policies can override the default matrix for their scope. The default is
deliberately tight enough that an un-overridden HIPAA skill will not satisfy
it without declaring a complete risk profile and meeting org-tier controls.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from skillctl.skill_yaml import RiskLevel, SideEffects
from skillctl.strictness import Strictness


@dataclass(frozen=True)
class RiskMatrixCell:
    """Required controls for one (strictness, risk_level) cell."""

    strictness: str
    risk_level: str
    # `allowed=False` means: this combination is refused. A `critical` skill
    # at `local` strictness blocks because there's no enforcement infrastructure
    # to make `critical` operations safe at that rung.
    allowed: bool = True
    rationale: str = ""

    require_injection_corpus: bool = False
    require_human_approval: bool = False
    require_signed_bundle: bool = False
    require_sandbox: bool = False
    require_security_reviewer: bool = False
    max_side_effects: str = ""             # one of SideEffects values; "" = no cap


# ── default matrix ──────────────────────────────────────────────────────────


def _cell(strictness: Strictness, risk: RiskLevel, **kwargs) -> RiskMatrixCell:
    return RiskMatrixCell(
        strictness=strictness.value,
        risk_level=risk.value,
        **kwargs,
    )


# 16 cells. Each row demonstrates the design: cumulative controls per axis.
# A higher risk_level inherits the lower-risk row's controls at the same
# strictness. A higher strictness inherits the lower strictness's controls
# at the same risk_level. The matrix encodes the cumulative requirements
# directly rather than relying on inheritance so the values are explicit
# in the audit report.

DEFAULT_RISK_MATRIX: dict[tuple[str, str], RiskMatrixCell] = {
    # ── local — solo dev, prototyping, friction-minimal ──────────────────
    (Strictness.LOCAL.value, RiskLevel.LOW.value): _cell(
        Strictness.LOCAL, RiskLevel.LOW,
        rationale="Solo prototyping. No formal controls required.",
    ),
    (Strictness.LOCAL.value, RiskLevel.MEDIUM.value): _cell(
        Strictness.LOCAL, RiskLevel.MEDIUM,
        rationale="Solo prototyping with limited blast radius.",
    ),
    (Strictness.LOCAL.value, RiskLevel.HIGH.value): _cell(
        Strictness.LOCAL, RiskLevel.HIGH,
        rationale="A high-risk skill at local strictness must declare human-approval intent.",
        require_human_approval=True,
        max_side_effects=SideEffects.REVERSIBLE.value,
    ),
    (Strictness.LOCAL.value, RiskLevel.CRITICAL.value): _cell(
        Strictness.LOCAL, RiskLevel.CRITICAL,
        allowed=False,
        rationale=(
            "A critical-risk skill cannot ship at local strictness. "
            "Climb the ladder to `team` (or higher) to satisfy the controls."
        ),
    ),

    # ── team — small-team workflows, light marketplace ───────────────────
    (Strictness.TEAM.value, RiskLevel.LOW.value): _cell(
        Strictness.TEAM, RiskLevel.LOW,
        rationale="Shared team skill, low blast radius.",
    ),
    (Strictness.TEAM.value, RiskLevel.MEDIUM.value): _cell(
        Strictness.TEAM, RiskLevel.MEDIUM,
        rationale="Shared team skill with material side effects.",
        require_injection_corpus=True,
    ),
    (Strictness.TEAM.value, RiskLevel.HIGH.value): _cell(
        Strictness.TEAM, RiskLevel.HIGH,
        rationale="High-risk team skill needs documented approval intent and injection coverage.",
        require_injection_corpus=True,
        require_human_approval=True,
        max_side_effects=SideEffects.EXTERNAL.value,
    ),
    (Strictness.TEAM.value, RiskLevel.CRITICAL.value): _cell(
        Strictness.TEAM, RiskLevel.CRITICAL,
        rationale="Critical-risk team skill — needs the full team-tier control set plus a signed bundle.",
        require_injection_corpus=True,
        require_human_approval=True,
        require_signed_bundle=True,
        max_side_effects=SideEffects.EXTERNAL.value,
    ),

    # ── org — production-internal ─────────────────────────────────────────
    (Strictness.ORG.value, RiskLevel.LOW.value): _cell(
        Strictness.ORG, RiskLevel.LOW,
        rationale="Production-internal low-risk skill — injection coverage required at minimum.",
        require_injection_corpus=True,
    ),
    (Strictness.ORG.value, RiskLevel.MEDIUM.value): _cell(
        Strictness.ORG, RiskLevel.MEDIUM,
        rationale="Production-internal with material side effects.",
        require_injection_corpus=True,
        require_signed_bundle=True,
    ),
    (Strictness.ORG.value, RiskLevel.HIGH.value): _cell(
        Strictness.ORG, RiskLevel.HIGH,
        rationale="Production-internal high-risk skill — requires security review.",
        require_injection_corpus=True,
        require_signed_bundle=True,
        require_human_approval=True,
        require_security_reviewer=True,
        max_side_effects=SideEffects.EXTERNAL.value,
    ),
    (Strictness.ORG.value, RiskLevel.CRITICAL.value): _cell(
        Strictness.ORG, RiskLevel.CRITICAL,
        rationale="Critical-risk production skill — full org control set + runtime sandbox.",
        require_injection_corpus=True,
        require_signed_bundle=True,
        require_human_approval=True,
        require_security_reviewer=True,
        require_sandbox=True,
        max_side_effects=SideEffects.EXTERNAL.value,
    ),

    # ── regulated — strictest, HIPAA-style ───────────────────────────────
    (Strictness.REGULATED.value, RiskLevel.LOW.value): _cell(
        Strictness.REGULATED, RiskLevel.LOW,
        rationale="Even a low-risk regulated skill needs signed bundles and injection coverage.",
        require_injection_corpus=True,
        require_signed_bundle=True,
    ),
    (Strictness.REGULATED.value, RiskLevel.MEDIUM.value): _cell(
        Strictness.REGULATED, RiskLevel.MEDIUM,
        rationale="Medium-risk regulated skill — human approval required.",
        require_injection_corpus=True,
        require_signed_bundle=True,
        require_human_approval=True,
    ),
    (Strictness.REGULATED.value, RiskLevel.HIGH.value): _cell(
        Strictness.REGULATED, RiskLevel.HIGH,
        rationale="High-risk regulated skill — full control set including sandbox.",
        require_injection_corpus=True,
        require_signed_bundle=True,
        require_human_approval=True,
        require_security_reviewer=True,
        require_sandbox=True,
        max_side_effects=SideEffects.EXTERNAL.value,
    ),
    (Strictness.REGULATED.value, RiskLevel.CRITICAL.value): _cell(
        Strictness.REGULATED, RiskLevel.CRITICAL,
        rationale="Maximum-control profile — every gate engaged.",
        require_injection_corpus=True,
        require_signed_bundle=True,
        require_human_approval=True,
        require_security_reviewer=True,
        require_sandbox=True,
        max_side_effects=SideEffects.EXTERNAL.value,
    ),
}


# ── lookup ──────────────────────────────────────────────────────────────────


def get_matrix_cell(
    strictness: Strictness, risk_level: RiskLevel
) -> RiskMatrixCell:
    """Look up the matrix cell for a (strictness, risk) pair.

    Returns a permissive default cell if the lookup misses — this is
    defensive: a future strictness or risk level that lands without a
    matrix entry should not crash the validator.
    """
    key = (strictness.value, risk_level.value)
    cell = DEFAULT_RISK_MATRIX.get(key)
    if cell is not None:
        return cell
    # Defensive default — unknown cells are allowed with no extra controls.
    return RiskMatrixCell(
        strictness=strictness.value,
        risk_level=risk_level.value,
        rationale="cell missing from matrix; defaulting to permissive",
    )


# ── render for `bbsctl risk show` / report consumers ────────────────────────


@dataclass(frozen=True)
class RenderedRow:
    """One row of the matrix in display form. Used by `bbsctl risk` later."""

    strictness: str
    risk_level: str
    allowed: bool
    controls: list[str] = field(default_factory=list)
    rationale: str = ""


def render_matrix() -> list[RenderedRow]:
    """Render the default matrix as a flat list, sorted by (strictness, risk)."""
    order_strict = [s.value for s in Strictness]
    order_risk = [r.value for r in RiskLevel]
    rows: list[RenderedRow] = []
    for s in order_strict:
        for r in order_risk:
            cell = DEFAULT_RISK_MATRIX.get((s, r))
            if cell is None:
                continue
            controls = [c for c, on in (
                ("injection_corpus", cell.require_injection_corpus),
                ("human_approval", cell.require_human_approval),
                ("signed_bundle", cell.require_signed_bundle),
                ("sandbox", cell.require_sandbox),
                ("security_reviewer", cell.require_security_reviewer),
            ) if on]
            if cell.max_side_effects:
                controls.append(f"max_side_effects={cell.max_side_effects}")
            rows.append(
                RenderedRow(
                    strictness=s,
                    risk_level=r,
                    allowed=cell.allowed,
                    controls=controls,
                    rationale=cell.rationale,
                )
            )
    return rows


__all__ = [
    "DEFAULT_RISK_MATRIX",
    "RenderedRow",
    "RiskMatrixCell",
    "get_matrix_cell",
    "render_matrix",
]
