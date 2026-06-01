"""ValidateRunner — orchestrates the validator chain for a skill directory.

Phase 2 fast validators (team strictness):
  enterprise-spec      skill.yaml present + valid
  basic-trigger        name/description trigger quality
  output-contract      output_contract well-formed if present

Phase 3 full validators (org strictness) are registered via register_validator()
at import time when the org modules land (not wired yet).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skillctl.strictness import Strictness

from .base import ValidateMode, ValidateResult, Validator, ValidatorResult
from .basic_trigger import BasicTriggerValidator
from .enterprise_spec import EnterpriseSpecValidator
from .output_contract import OutputContractValidator
from .ownership_validator import OwnershipValidator
from .permissions_validator import PermissionsValidator
from .policy_validator import PolicyValidator


@dataclass(frozen=True)
class _ValidatorRegistration:
    factory: Callable[[], Validator]
    min_mode: ValidateMode  # FAST = always; FULL = only with --full


# Phase 2 fast validators.
_REGISTRY: list[_ValidatorRegistration] = [
    _ValidatorRegistration(factory=EnterpriseSpecValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=BasicTriggerValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=OutputContractValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=PermissionsValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=OwnershipValidator, min_mode=ValidateMode.FAST),
    _ValidatorRegistration(factory=PolicyValidator, min_mode=ValidateMode.FAST),
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
    ) -> None:
        self._skill_dir = skill_dir
        self._strictness = strictness
        self._mode = mode

    def run(self) -> ValidateResult:
        results: list[ValidatorResult] = []

        for reg in _REGISTRY:
            if self._mode == ValidateMode.FAST and reg.min_mode == ValidateMode.FULL:
                continue

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
