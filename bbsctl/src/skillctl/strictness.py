"""The strictness axis — see framework-build-plan.md §1.

Strictness is orthogonal to trust tier. It declares how much friction the
author has agreed to: the framework asks for more (validators, ownership,
signing, etc.) as the author climbs the ladder.

Used as the configuration key for every factory in this codebase. The compile
pipeline, the validator chain, the marketplace gate, the runtime hooks all
take Strictness as input and choose their behavior accordingly.

This module also tracks which strictness levels are *currently supported* by
each subcommand. The friction audit (docs/audits/phase-1.md F2/F3) caught a
"vapor-options" pattern where argparse advertised levels with no real
implementation. The `supported_levels()` registry is how each subcommand
restricts its `--strictness` choices to honest values.
"""

from __future__ import annotations

from enum import StrEnum


class Strictness(StrEnum):
    """Declared author-side strictness level.

    Inherits from str so it serializes naturally to JSON/YAML and compares
    with string literals when configs come from disk.
    """

    LOCAL = "local"
    TEAM = "team"
    ORG = "org"
    REGULATED = "regulated"

    @classmethod
    def from_string(cls, value: str | None) -> Strictness:
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

    def includes(self, other: Strictness) -> bool:
        """Returns True if this strictness level requires everything `other` does.

        Used for cumulative checks: "does this skill at `org` need what `team` needs?"
        """
        order = [self.LOCAL, self.TEAM, self.ORG, self.REGULATED]
        return order.index(self) >= order.index(other)


# Phase-aware support registry. Each entry names a subcommand and the set of
# strictness levels that subcommand actually honours today. Argparse uses this
# to populate its `choices=` so unimplemented levels do not leak through.
# The vapor-options lint test (tests/test_vapor_options.py) walks this same
# registry to assert CLI choices and implementations agree.
_SUPPORTED: dict[str, set[Strictness]] = {
    # Phase 1 ships the `local` template only; team/org/regulated land in Phase 2+.
    "new": {Strictness.LOCAL},
    # Compile runs the same step set at every strictness today (every registered
    # step has `applies_at = LOCAL`). When higher-strictness steps register in
    # Phase 2+, this set widens.
    "compile": {Strictness.LOCAL},
    # The publish gate enforces `target.min_strictness` separately; the CLI
    # `--strictness` override is meaningful at every level today.
    "publish": {Strictness.LOCAL, Strictness.TEAM, Strictness.ORG, Strictness.REGULATED},
}


def supported_levels(subcommand: str) -> list[str]:
    """Return the strictness level values supported by `subcommand`, in canonical order.

    Used by argparse to populate `choices=`. Unsupported levels are NOT shown,
    eliminating the vapor-options pattern caught by the Phase 1 friction audit.
    """
    levels = _SUPPORTED.get(subcommand, {Strictness.LOCAL})
    order = (Strictness.LOCAL, Strictness.TEAM, Strictness.ORG, Strictness.REGULATED)
    return [s.value for s in order if s in levels]


def register_support(subcommand: str, *levels: Strictness) -> None:
    """Mark additional strictness levels as supported for a subcommand.

    Called by phase-N modules when their implementations are wired in. For
    example, when Phase 2 lands the `team` template, it calls:

        register_support("new", Strictness.TEAM)
    """
    _SUPPORTED.setdefault(subcommand, set()).update(levels)


def fail_if_unsupported(subcommand: str, level: Strictness) -> str | None:
    """Return a Fix message if `level` is unsupported for `subcommand`, else None.

    Subcommands call this defensively so even if argparse choices are bypassed
    (e.g. through programmatic invocation), the framework emits a helpful error.
    """
    if level.value in supported_levels(subcommand):
        return None
    supported = ", ".join(supported_levels(subcommand))
    return (
        f"strictness `{level.value}` is not supported by `bbsctl {subcommand}` yet "
        f"(Phase 1 supports: {supported}). The strictness ladder rolls out across phases "
        f"— see docs/strictness-levels.md."
    )


__all__ = [
    "Strictness",
    "fail_if_unsupported",
    "register_support",
    "supported_levels",
]
