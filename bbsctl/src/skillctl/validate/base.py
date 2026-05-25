"""Validator strategy interface and result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from skillctl.messaging import FrameworkError
from skillctl.strictness import Strictness


class ValidateMode(StrEnum):
    FAST = "fast"    # team-tier sub-validators: spec, trigger, output-contract
    FULL = "full"    # Phase 3: + registry-context trigger, injection corpus, fuzzer


@dataclass
class ValidatorResult:
    """Result from one Validator.run()."""

    validator_name: str
    passed: bool
    duration_ms: int = 0
    errors: list[FrameworkError] = field(default_factory=list)
    warnings: list[FrameworkError] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ValidateResult:
    """Aggregated result from a full validate run."""

    passed: bool
    skill_dir: Path
    strictness: Strictness
    mode: ValidateMode
    results: list[ValidatorResult] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        return sum(len(r.errors) for r in self.results)

    @property
    def total_warnings(self) -> int:
        return sum(len(r.warnings) for r in self.results)


class Validator(ABC):
    """Strategy interface for a single fast validator."""

    #: Short name used in reports and error messages.
    name: str = "anonymous-validator"

    def applies_to(self, strictness: Strictness) -> bool:
        """Return False to skip this validator at a given strictness level."""
        return True

    @abstractmethod
    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        """Execute the validator. Must not raise for user errors."""


__all__ = ["ValidateMode", "ValidateResult", "Validator", "ValidatorResult"]
