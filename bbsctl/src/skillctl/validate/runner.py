"""ValidateRunner — orchestrates the validator chain for a skill directory.

Phase 2 fast validators (team strictness):
  enterprise-spec      skill.yaml present + valid
  basic-trigger        name/description trigger quality
  output-contract      output_contract well-formed if present

Phase 3 full validators (org strictness) are registered via register_validator()
at import time when the org modules land (not wired yet).

FULL also runs IntraSkillConflictValidator (polarity tags; optional LLM).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skillctl.strictness import Strictness

from .base import ValidateMode, ValidateResult, Validator, ValidatorResult
from .basic_trigger import BasicTriggerValidator
from .enterprise_spec import EnterpriseSpecValidator
from .intra_skill_conflict import IntraSkillConflictValidator
from .output_contract import OutputContractValidator
from .ownership_validator import OwnershipValidator
from .permissions_validator import PermissionsValidator
from .policy_validator import PolicyValidator
from .risk_matrix_validator import RiskMatrixValidator


@dataclass(frozen=True)
class _ValidatorRegistration:
    factory: Callable[[], Validator]
    min_mode: ValidateMode  # FAST = always; FULL = only with --full
    # When set, ValidateRunner builds this validator with conflict options.
    conflict_aware: bool = False


# Phase 2 fast validators.
_REGISTRY: list[_ValidatorRegistration] = [
    _ValidatorRegistration(factory=EnterpriseSpecValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=BasicTriggerValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=OutputContractValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=PermissionsValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=OwnershipValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=PolicyValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=RiskMatrixValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(
        factory=IntraSkillConflictValidator,
        min_mode=ValidateMode.FULL,
        conflict_aware=True,
    ),
]


def register_validator(
    factory: Callable[[], Validator],
    *,
    min_mode: ValidateMode = ValidateMode.FAST,
) -> None:
    """Register a validator for Phase 3+ full validate.

    Called at module import time from org-strictness modules.
    """
    _REGISTRY.append(_ValidatorRegistration(factory=factory, min_mode=min_mode))


class ValidateRunner:
    """Run the appropriate validator chain for a skill directory.

    mode=FAST  runs only the fast validators (< 10s target, ADR acceptance #2)
    mode=FULL  runs all registered validators (Phase 3 adds the heavy ones)
    """

    def __init__(
        self,
        skill_dir: Path,
        strictness: Strictness,
        *,
        mode: ValidateMode = ValidateMode.FAST,
        conflict_classifier: str = "heuristic",
        llm_backend: str | None = None,
        llm_model: str | None = None,
        conflict_llm: object | None = None,
    ) -> None:
        self._skill_dir = skill_dir
        self._strictness = strictness
        self._mode = mode
        self._conflict_classifier = conflict_classifier
        self._llm_backend = llm_backend
        self._llm_model = llm_model
        self._conflict_llm = conflict_llm

    def run(self) -> ValidateResult:
        results: list[ValidatorResult] = []

        for reg in _REGISTRY:
            if self._mode == ValidateMode.FAST and reg.min_mode == ValidateMode.FULL:
                continue

            if reg.conflict_aware:
                validator: Validator = IntraSkillConflictValidator(
                    classifier=self._conflict_classifier,
                    backend=self._llm_backend,
                    model=self._llm_model,
                    llm_backend=self._conflict_llm,
                )
            else:
                validator = reg.factory()
            if not validator.applies_to(self._strictness):
                continue

            result = validator.run(self._skill_dir, self._strictness)
            results.append(result)

        passed = all(r.passed for r in results)
        return ValidateResult(
            passed=passed,
            skill_dir=self._skill_dir,
            strictness=self._strictness,
            mode=self._mode,
            results=results,
        )


__all__ = ["ValidateRunner", "register_validator"]
