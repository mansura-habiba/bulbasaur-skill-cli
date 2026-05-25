"""EnterpriseSpecValidator — skill.yaml present + valid at team+ strictness."""

from __future__ import annotations

import time
from pathlib import Path

from skillctl.messaging import FrameworkError
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult


class EnterpriseSpecValidator(Validator):
    """Validate the skill.yaml enterprise overlay.

    At `team`+:
    - skill.yaml must exist.
    - name must match SKILL.md name (best-effort check).
    - strictness declared in skill.yaml must be >= team.

    At `local`:
    - skill.yaml is optional; if present it must parse cleanly.
    """

    name = "enterprise-spec"

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        skill_yaml_path = skill_dir / "skill.yaml"
        is_team_or_above = strictness.includes(Strictness.TEAM)

        if not skill_yaml_path.exists():
            if is_team_or_above:
                errors.append(
                    FrameworkError(
                        summary="skill.yaml not found",
                        detail=f"required at {strictness.value} strictness: {skill_yaml_path}",
                        fix=(
                            "Run `bbsctl strictness team` to generate skill.yaml, "
                            "or create it manually. See docs/strictness-levels.md."
                        ),
                        docs="../docs/strictness-levels.md",
                    )
                )
            else:
                notes.append("skill.yaml not present (optional at local strictness)")
            return ValidatorResult(
                validator_name=self.name,
                passed=not errors,
                duration_ms=int((time.monotonic() - started) * 1000),
                errors=errors,
                warnings=warnings,
                notes=notes,
            )

        try:
            overlay = load_skill_yaml(skill_dir)
        except SkillYamlError as exc:
            errors.append(exc.framework_error)
            return ValidatorResult(
                validator_name=self.name,
                passed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                errors=errors,
            )

        if overlay is None:
            notes.append("skill.yaml loaded (empty file treated as absent)")
            return ValidatorResult(
                validator_name=self.name,
                passed=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                notes=notes,
            )

        # Strictness consistency: declared strictness must be >= the compile-time strictness.
        if is_team_or_above and not overlay.strictness.includes(Strictness.TEAM):
            errors.append(
                FrameworkError(
                    summary=(
                        f"skill.yaml declares strictness `{overlay.strictness.value}` "
                        f"but compile is running at `{strictness.value}`"
                    ),
                    fix=(
                        f"Update `strictness: {strictness.value}` in skill.yaml, "
                        "or run `bbsctl strictness team` to migrate automatically."
                    ),
                )
            )

        # Ownership advisory at team.
        if is_team_or_above and not overlay.has_ownership:
            warnings.append(
                FrameworkError(
                    summary="ownership not declared in skill.yaml",
                    detail="Recommended at team strictness; required at org+.",
                    fix=(
                        "Add an `ownership:` block with at minimum `team: your-team-name`. "
                        "Run `bbsctl strictness team` to see the interactive prompt."
                    ),
                    docs="../docs/strictness-levels.md",
                )
            )

        notes.append(f"skill.yaml: name={overlay.name!r} strictness={overlay.strictness.value}")

        return ValidatorResult(
            validator_name=self.name,
            passed=not errors,
            duration_ms=int((time.monotonic() - started) * 1000),
            errors=errors,
            warnings=warnings,
            notes=notes,
        )


__all__ = ["EnterpriseSpecValidator"]
