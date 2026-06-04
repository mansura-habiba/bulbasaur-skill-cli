"""RiskMatrixValidator — enforce the (strictness × risk_level) matrix.

The matrix lives in `skillctl.risk_matrix`. This validator looks up the
skill's declared `(strictness, risk.level)` cell and checks every required
control. Unknown cells (e.g. a skill that hasn't declared `risk.level`)
surface a structured warning so the author knows what was — or wasn't —
checked.
"""

from __future__ import annotations

import time
from pathlib import Path

from skillctl.messaging import FrameworkError
from skillctl.risk_matrix import RiskMatrixCell, get_matrix_cell
from skillctl.skill_yaml import (
    SideEffects,
    SkillYamlError,
    load_skill_yaml,
)
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult


class RiskMatrixValidator(Validator):
    """Compare the skill's declared (strictness × risk.level) cell against the matrix."""

    name = "risk-matrix"

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        try:
            overlay = load_skill_yaml(skill_dir)
        except SkillYamlError as exc:
            return _result(
                self.name, started, errors=[exc.framework_error]
            )

        if overlay is None:
            # Local strictness: skill.yaml is optional; matrix checks
            # don't apply because risk can't be declared.
            notes.append("no skill.yaml — risk-matrix check skipped")
            return _result(self.name, started, notes=notes)

        risk = overlay.risk
        if risk.level is None:
            if strictness.includes(Strictness.ORG):
                errors.append(
                    FrameworkError(
                        summary=(
                            "risk-matrix: skill.yaml `risk.level` is required at "
                            f"{strictness.value} strictness"
                        ),
                        fix=(
                            "Add a `risk:` block to skill.yaml with at least "
                            "`level: <low|medium|high|critical>`. "
                            "See docs/strictness-levels.md."
                        ),
                        docs="../docs/strictness-levels.md",
                    )
                )
            else:
                warnings.append(
                    FrameworkError(
                        summary="risk-matrix: `risk.level` not declared",
                        detail="Recommended at team; required at org+.",
                        fix=(
                            "Declare `risk.level` to enable framework checks "
                            "against the (strictness × risk) control matrix."
                        ),
                    )
                )
            return _result(
                self.name, started, errors=errors, warnings=warnings, notes=notes
            )

        cell = get_matrix_cell(strictness, risk.level)

        if not cell.allowed:
            errors.append(
                FrameworkError(
                    summary=(
                        f"risk-matrix: a `{risk.level.value}`-risk skill is "
                        f"refused at `{strictness.value}` strictness"
                    ),
                    detail=cell.rationale,
                    fix=(
                        "Either reduce the skill's `risk.level` (e.g. to `high`) "
                        "or climb the strictness ladder to a rung that admits "
                        "this risk level."
                    ),
                    docs="../docs/strictness-levels.md",
                )
            )
            return _result(
                self.name, started, errors=errors, warnings=warnings, notes=notes
            )

        # Required controls.
        if cell.require_injection_corpus:
            ok = (skill_dir / "evals" / "injection.json").is_file()
            if not ok:
                errors.append(
                    FrameworkError(
                        summary=(
                            f"risk-matrix: cell ({strictness.value}, {risk.level.value}) "
                            "requires evals/injection.json"
                        ),
                        fix=(
                            "Create evals/injection.json. The framework's default "
                            "corpus can be written with "
                            "`from skillctl.eval.injection_corpus import write_default_corpus`."
                        ),
                    )
                )

        if cell.require_human_approval and not risk.requires_human_approval:
            errors.append(
                FrameworkError(
                    summary=(
                        f"risk-matrix: cell ({strictness.value}, {risk.level.value}) "
                        "requires `risk.requires_human_approval: true` in skill.yaml"
                    ),
                    fix="Add `requires_human_approval: true` to the skill.yaml `risk:` block.",
                )
            )

        if cell.require_signed_bundle:
            # The bundle is created at publish time, not present in the
            # source tree. Surface as WARNING here so validate doesn't
            # block; the publish gate enforces.
            warnings.append(
                FrameworkError(
                    summary=(
                        f"risk-matrix: cell ({strictness.value}, {risk.level.value}) "
                        "requires a Sigstore-signed bundle (verified at publish time)"
                    ),
                    detail="Sigstore signing wires into bundle.sig in Phase 3.",
                )
            )

        if cell.require_sandbox:
            warnings.append(
                FrameworkError(
                    summary=(
                        f"risk-matrix: cell ({strictness.value}, {risk.level.value}) "
                        "requires a runtime sandbox (enforced by the hook bus, Phase 4)"
                    ),
                )
            )

        if cell.require_security_reviewer:
            # Defer to ownership validator for the actual reviewer presence
            # check; surface as note here.
            notes.append(
                f"risk-matrix: security reviewer required at "
                f"({strictness.value}, {risk.level.value}); verified by ownership validator"
            )

        if cell.max_side_effects and risk.side_effects is not None:
            order = [
                SideEffects.NONE,
                SideEffects.READ_ONLY,
                SideEffects.REVERSIBLE,
                SideEffects.EXTERNAL,
                SideEffects.DESTRUCTIVE,
            ]
            cap = SideEffects.from_string(cell.max_side_effects)
            if cap is not None and risk.side_effects in order:
                if order.index(risk.side_effects) > order.index(cap):
                    errors.append(
                        FrameworkError(
                            summary=(
                                f"risk-matrix: cell ({strictness.value}, {risk.level.value}) "
                                f"caps `side_effects` at `{cap.value}`; declared `{risk.side_effects.value}`"
                            ),
                            fix=(
                                f"Reduce the skill's `risk.side_effects` to `{cap.value}` "
                                "(or lower) — or downgrade `risk.level` if the side-effect "
                                "profile is genuinely beyond the cap."
                            ),
                        )
                    )

        if not errors:
            notes.append(
                f"risk-matrix: ({strictness.value}, {risk.level.value}) PASSED  "
                f"controls applied: "
                f"injection={cell.require_injection_corpus} "
                f"approval={cell.require_human_approval} "
                f"signed={cell.require_signed_bundle} "
                f"sandbox={cell.require_sandbox} "
                f"reviewer={cell.require_security_reviewer} "
                f"max_se={cell.max_side_effects or 'unset'}"
            )

        return _result(
            self.name, started, errors=errors, warnings=warnings, notes=notes
        )


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


__all__ = ["RiskMatrixValidator"]
