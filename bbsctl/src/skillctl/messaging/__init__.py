"""The Bulbasaur error-message contract.

Every framework error printed to the user MUST be constructed through this module.
The DX charter (framework-build-plan.md §0.2) requires ≥90% of errors to carry
a copy-pasteable Fix line; the audit happens against this catalog.

Shape:

    ERROR: <one-line summary>
      Detail: <what went wrong, where>
      Fix:    <copy-pasteable remediation>
      Docs:   <link to relevant doc, if applicable>

Detail/Fix/Docs are all optional, but Fix is strongly encouraged. The contract
is enforced by the lint check in skillctl/tests/test_error_contract.py.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class FrameworkError:
    """A user-facing error with the Bulbasaur formatting contract.

    Construct one of these instead of raising a bare exception when the failure
    should be surfaced to the developer with a remediation. The framework's
    exit-code policy: 0 for success, 1 for user error (this module), 2 for
    framework internal error (bare exception, "please report" message).
    """

    summary: str
    detail: str | None = None
    fix: str | None = None
    docs: str | None = None

    def render(self) -> str:
        lines = [f"ERROR: {self.summary}"]
        if self.detail:
            lines.append(f"  Detail: {self.detail}")
        if self.fix:
            # Wrap the Fix at sensible column to keep terminal output readable.
            lines.append(f"  Fix:    {self.fix}")
        if self.docs:
            lines.append(f"  Docs:   {self.docs}")
        return "\n".join(lines)


def emit(error: FrameworkError, *, stream=None) -> None:
    """Print a FrameworkError to stderr (or the given stream) and return.

    Does not exit. The caller decides whether to continue or exit; tests can
    capture multiple emits in one run.
    """
    stream = stream if stream is not None else sys.stderr
    print(error.render(), file=stream)


def emit_and_exit(error: FrameworkError, *, code: int = 1) -> None:
    """Print a FrameworkError to stderr and exit with the given code (default 1)."""
    emit(error)
    sys.exit(code)


def info(message: str, *, stream=None) -> None:
    """Print an informational message. Use sparingly; CLI output should be quiet by default."""
    stream = stream if stream is not None else sys.stdout
    print(message, file=stream)


__all__ = ["FrameworkError", "emit", "emit_and_exit", "info"]
