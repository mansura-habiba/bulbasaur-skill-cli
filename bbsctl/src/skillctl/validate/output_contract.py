"""OutputContractValidator — output_contract schema is well-formed if present.

At team strictness, output_contract in skill.yaml is recommended but not
required. If it is declared, we check:

1. `output` key is a dict (JSON Schema object).
2. `output.type` is a recognized JSON Schema type if present.
3. If `output.properties` is present, it is a non-empty dict.

Full JSON Schema Draft-7 validation and composition planner type-checking land
in Phase 3 (org strictness).
"""

from __future__ import annotations

import time
from pathlib import Path

from skillctl.messaging import FrameworkError
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult

_VALID_TYPES = frozenset(
    {"string", "number", "integer", "boolean", "array", "object", "null"}
)


class OutputContractValidator(Validator):
    """Check output_contract in skill.yaml is well-formed."""

    name = "output-contract"

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        skill_yaml_path = skill_dir / "skill.yaml"
        if not skill_yaml_path.exists():
            notes.append("skill.yaml absent; output_contract check skipped")
            return ValidatorResult(
                validator_name=self.name,
                passed=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                notes=notes,
            )

        try:
            overlay = load_skill_yaml(skill_dir)
        except SkillYamlError as exc:
            # EnterpriseSpecValidator already reported parse errors; don't double-report.
            notes.append(f"skill.yaml parse error (reported by enterprise-spec): {exc}")
            return ValidatorResult(
                validator_name=self.name,
                passed=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                notes=notes,
            )

        if overlay is None or overlay.output_contract is None:
            notes.append("no output_contract declared (optional at team strictness)")
            return ValidatorResult(
                validator_name=self.name,
                passed=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                notes=notes,
            )

        oc = overlay.output_contract
        output_schema = oc.output

        # Check 1: must be a dict.
        if not isinstance(output_schema, dict):
            errors.append(
                FrameworkError(
                    summary="output_contract.output must be a JSON Schema object (dict)",
                    detail=f"got {type(output_schema).__name__}",
                    fix=(
                        "output_contract.output should be a JSON Schema dict, e.g.:\n"
                        "  output_contract:\n"
                        "    output:\n"
                        "      type: object\n"
                        "      properties:\n"
                        "        summary: {type: string}"
                    ),
                )
            )
            return ValidatorResult(
                validator_name=self.name,
                passed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                errors=errors,
            )

        # Check 2: type, if present, is valid.
        declared_type = output_schema.get("type")
        if declared_type is not None:
            if isinstance(declared_type, list):
                invalid = [t for t in declared_type if t not in _VALID_TYPES]
                if invalid:
                    errors.append(
                        FrameworkError(
                            summary=(
                                "output_contract.output.type contains "
                                f"unknown types: {invalid}"
                            ),
                            fix=f"Valid JSON Schema types: {sorted(_VALID_TYPES)}",
                        )
                    )
            elif declared_type not in _VALID_TYPES:
                errors.append(
                    FrameworkError(
                        summary=(
                            f"output_contract.output.type `{declared_type}` "
                            "is not a valid JSON Schema type"
                        ),
                        fix=f"Valid types: {sorted(_VALID_TYPES)}",
                    )
                )

        # Check 3: properties, if present, is a non-empty dict.
        props = output_schema.get("properties")
        if props is not None:
            if not isinstance(props, dict) or not props:
                warnings.append(
                    FrameworkError(
                        summary="output_contract.output.properties is empty or not a dict",
                        fix="Either remove `properties` or add at least one property definition.",
                    )
                )

        notes.append(
            f"output_contract present: type={declared_type!r} "
            f"props={list(props.keys()) if isinstance(props, dict) else None}"
        )

        return ValidatorResult(
            validator_name=self.name,
            passed=not errors,
            duration_ms=int((time.monotonic() - started) * 1000),
            errors=errors,
            warnings=warnings,
            notes=notes,
        )


__all__ = ["OutputContractValidator"]
