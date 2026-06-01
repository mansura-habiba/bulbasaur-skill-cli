"""PolicyValidator — runs every declared policy through the PolicyEngine.

Skills declare policies in skill.yaml:

    policies:
      - hipaa-baseline          # short name → resolved from the bundled catalog
      - ./policies/internal.yaml  # local path
      - /abs/path/to/policy.yaml  # absolute path

At `org`+ strictness the validator additionally requires at least one
applicable policy. The validator merges all applicable policies (deny-wins)
and runs `PolicyEngine.validate()` once on the merged result so the report
attribution is consistent across multi-policy skills.
"""

from __future__ import annotations

import time
from pathlib import Path

from skillctl.messaging import FrameworkError
from skillctl.policy import (
    PolicyEngine,
    PolicyLoadError,
    load_policy,
    merge_policies,
)
from skillctl.policy.base import CheckOutcome, Policy
from skillctl.policy.catalog import resolve_catalog_path
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult


class PolicyValidator(Validator):
    """Validate a skill against every policy it declares."""

    name = "policy"

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

        declared = list(overlay.policies) if overlay else []

        if not declared:
            if strictness.includes(Strictness.ORG):
                errors.append(
                    FrameworkError(
                        summary=(
                            "policy: no policies declared at "
                            f"`{strictness.value}` strictness"
                        ),
                        fix=(
                            "Add a `policies:` list to skill.yaml with at least one "
                            "policy. Use `bbsctl policy list` to see bundled "
                            "policies (e.g. `hipaa-baseline`, `soc2-type2-baseline`, "
                            "`internal-tier-1`)."
                        ),
                        docs="../docs/policy.md",
                    )
                )
            else:
                notes.append("no policies declared (optional at this strictness)")
            return _result(
                self.name, started, errors=errors, warnings=warnings, notes=notes
            )

        # Load each declared policy. Failures become errors.
        loaded: list[Policy] = []
        for ref in declared:
            path = _resolve_policy_path(ref, skill_dir=skill_dir)
            if path is None:
                errors.append(
                    FrameworkError(
                        summary=f"policy: cannot resolve `{ref}`",
                        fix=(
                            "Check the policy name or path. Bundled names are "
                            "listed by `bbsctl policy list`."
                        ),
                    )
                )
                continue
            try:
                loaded.append(load_policy(path))
            except PolicyLoadError as exc:
                errors.append(exc.framework_error)

        if errors:
            return _result(
                self.name, started, errors=errors, warnings=warnings, notes=notes
            )

        merged = merge_policies(*loaded) if len(loaded) > 1 else loaded[0]
        result = PolicyEngine(merged).validate(skill_dir, strictness)

        # Translate RequirementCheck → ValidatorResult shape.
        for check in result.checks:
            if check.outcome == CheckOutcome.FAIL:
                errors.append(
                    FrameworkError(
                        summary=(
                            f"policy `{result.policy_name}`: "
                            f"{check.requirement}"
                        ),
                        detail=check.detail,
                        fix=check.fix,
                    )
                )
            elif check.outcome == CheckOutcome.UNKNOWN:
                warnings.append(
                    FrameworkError(
                        summary=(
                            f"policy `{result.policy_name}`: "
                            f"{check.requirement} (deferred to publish/runtime)"
                        ),
                        detail=check.detail,
                    )
                )

        notes.append(
            f"policy `{result.policy_name}`: "
            f"{result.passed_checks} pass · "
            f"{len(result.failures)} fail · "
            f"{len(result.warnings)} deferred  "
            f"({len(declared)} policy/policies declared)"
        )

        return _result(
            self.name, started, errors=errors, warnings=warnings, notes=notes
        )


def _resolve_policy_path(ref: str, *, skill_dir: Path) -> Path | None:
    """Resolve a policy reference to an on-disk YAML file.

    Resolution order:
      1. Catalog short name (`hipaa-baseline` → bundled YAML)
      2. Absolute path
      3. Path relative to the skill directory
      4. Path relative to the current working directory
    """
    catalog_path = resolve_catalog_path(ref)
    if catalog_path is not None:
        return catalog_path

    p = Path(ref)
    if p.is_absolute() and p.is_file():
        return p

    relative_to_skill = (skill_dir / ref).resolve()
    if relative_to_skill.is_file():
        return relative_to_skill

    relative_to_cwd = Path.cwd() / ref
    if relative_to_cwd.is_file():
        return relative_to_cwd

    return None


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


__all__ = ["PolicyValidator"]
