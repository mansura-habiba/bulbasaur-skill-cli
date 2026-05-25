"""Phase 2 validator module.

`bbsctl validate --fast` runs the three team-tier sub-validators:
  EnterpriseSpecValidator   — skill.yaml present and valid at team+
  BasicTriggerValidator     — name/description form a useful trigger signal
  OutputContractValidator   — output_contract schema is well-formed (if present)

`bbsctl validate --full` (Phase 3) adds the registry-context trigger validator,
prompt-injection corpus, and semantic fuzzer. Those are not wired here yet.

Usage:
    from skillctl.validate import ValidateRunner, ValidateMode
    runner = ValidateRunner(skill_dir, strictness, mode=ValidateMode.FAST)
    result = runner.run()
"""

from .base import ValidateMode, ValidateResult, Validator, ValidatorResult
from .runner import ValidateRunner

__all__ = [
    "ValidateMode",
    "ValidateResult",
    "ValidateRunner",
    "Validator",
    "ValidatorResult",
]
