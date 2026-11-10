"""Phase 2 validator module.

`bbsctl validate --fast` runs the three team-tier sub-validators:
  EnterpriseSpecValidator   — skill.yaml present and valid at team+
  BasicTriggerValidator     — name/description form a useful trigger signal
  OutputContractValidator   — output_contract schema is well-formed (if present)

`bbsctl validate --full` adds IntraSkillConflictValidator (polarity tags;
optional LLM via --conflict-classifier llm) plus other Phase 3 validators
as they land.

Usage:
    from skillctl.validate import ValidateRunner, ValidateMode
    runner = ValidateRunner(skill_dir, strictness, mode=ValidateMode.FAST)
    result = runner.run()
"""

from .base import ValidateMode, ValidateResult, Validator, ValidatorResult
from .intra_skill_conflict import IntraSkillConflictValidator
from .runner import ValidateRunner

__all__ = [
    "IntraSkillConflictValidator",
    "ValidateMode",
    "ValidateResult",
    "ValidateRunner",
    "Validator",
    "ValidatorResult",
]
