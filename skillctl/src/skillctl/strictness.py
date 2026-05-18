"""The strictness axis — see framework-build-plan.md §1.

Strictness is orthogonal to trust tier. It declares how much friction the
author has agreed to: the framework asks for more (validators, ownership,
signing, etc.) as the author climbs the ladder.

Used as the configuration key for every factory in this codebase. The compile
pipeline, the validator chain, the marketplace gate, the runtime hooks all
take Strictness as input and choose their behavior accordingly.
"""

from __future__ import annotations

from enum import Enum


class Strictness(str, Enum):
    """Declared author-side strictness level.

    Inherits from str so it serializes naturally to JSON/YAML and compares
    with string literals when configs come from disk.
    """

    LOCAL = "local"
    TEAM = "team"
    ORG = "org"
    REGULATED = "regulated"

    @classmethod
    def from_string(cls, value: str | None) -> "Strictness":
        """Parse a strictness string, defaulting to LOCAL.

        Accepts None and unknown values by returning LOCAL — the safest default
        per the DX charter (defaults are permissive).
        """
        if not value:
            return cls.LOCAL
        try:
            return cls(value.lower())
        except ValueError:
            return cls.LOCAL

    def includes(self, other: "Strictness") -> bool:
        """Returns True if this strictness level requires everything `other` does.

        Used for cumulative checks: "does this skill at `org` need what `team` needs?"
        """
        order = [self.LOCAL, self.TEAM, self.ORG, self.REGULATED]
        return order.index(self) >= order.index(other)


__all__ = ["Strictness"]
