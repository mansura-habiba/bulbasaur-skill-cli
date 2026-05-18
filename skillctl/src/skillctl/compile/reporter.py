"""Reporter strategy for the compile pipeline.

The pipeline emits step-by-step progress through a Reporter. Three default
implementations:

  TextReporter   human-readable progress for interactive CLI use
  JsonReporter   structured output for CI / machine consumers
  NullReporter   silent (for tests, library use)

Adding a new reporter (JUnit XML, TAP, GitHub Actions annotations) is a matter
of subclassing Reporter and implementing the three hooks.
"""

from __future__ import annotations

import json
import sys
import time
from abc import ABC, abstractmethod
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline import CompileResult, StepResult


class Reporter(ABC):
    """Strategy interface for compile progress reporting."""

    @abstractmethod
    def on_start(self, *, skill_dir: str, strictness: str) -> None: ...

    @abstractmethod
    def on_step(self, step_name: str, result: "StepResult") -> None: ...

    @abstractmethod
    def on_finish(self, result: "CompileResult") -> None: ...


class TextReporter(Reporter):
    """Human-readable reporter for interactive CLI use.

    Prints one line per step plus a final summary. Errors are emitted using
    the Bulbasaur error contract (ERROR / Detail / Fix / Docs).
    """

    def __init__(self, stream: IO[str] | None = None):
        self._stream = stream or sys.stdout
        self._start_time: float | None = None

    def on_start(self, *, skill_dir: str, strictness: str) -> None:
        self._start_time = time.monotonic()
        print(f"skillctl compile  ·  {skill_dir}  ·  strictness={strictness}", file=self._stream)

    def on_step(self, step_name: str, result: "StepResult") -> None:
        # Step icons keep the output skimmable.
        icons = {"ok": "✓", "warned": "!", "failed": "✗", "skipped": "·"}
        icon = icons.get(result.outcome.value, "?")
        print(f"  {icon} {step_name}", file=self._stream)

        for warning in result.warnings:
            print("    " + warning.render().replace("\n", "\n    "), file=self._stream)
        for error in result.errors:
            print("    " + error.render().replace("\n", "\n    "), file=self._stream)

    def on_finish(self, result: "CompileResult") -> None:
        elapsed_ms = 0
        if self._start_time is not None:
            elapsed_ms = int((time.monotonic() - self._start_time) * 1000)
        status = "OK" if result.success else "FAILED"
        print(
            f"\ncompile {status}  ·  "
            f"{result.total_errors} error(s), {result.total_warnings} warning(s)  ·  "
            f"{elapsed_ms} ms",
            file=self._stream,
        )


class JsonReporter(Reporter):
    """JSON-line reporter for CI / machine consumers.

    Emits one JSON object per call. Consumers can stream-parse the output.
    """

    def __init__(self, stream: IO[str] | None = None):
        self._stream = stream or sys.stdout

    def _emit(self, payload: dict) -> None:
        print(json.dumps(payload, default=str), file=self._stream)

    def on_start(self, *, skill_dir: str, strictness: str) -> None:
        self._emit({"event": "start", "skill_dir": skill_dir, "strictness": strictness})

    def on_step(self, step_name: str, result: "StepResult") -> None:
        self._emit(
            {
                "event": "step",
                "name": step_name,
                "outcome": result.outcome.value,
                "warnings": [
                    {"summary": w.summary, "detail": w.detail, "fix": w.fix, "docs": w.docs}
                    for w in result.warnings
                ],
                "errors": [
                    {"summary": e.summary, "detail": e.detail, "fix": e.fix, "docs": e.docs}
                    for e in result.errors
                ],
            }
        )

    def on_finish(self, result: "CompileResult") -> None:
        self._emit(
            {
                "event": "finish",
                "success": result.success,
                "errors": result.total_errors,
                "warnings": result.total_warnings,
            }
        )


class NullReporter(Reporter):
    """Silent reporter for tests and library use."""

    def on_start(self, *, skill_dir: str, strictness: str) -> None:
        pass

    def on_step(self, step_name: str, result: "StepResult") -> None:
        pass

    def on_finish(self, result: "CompileResult") -> None:
        pass


__all__ = ["Reporter", "TextReporter", "JsonReporter", "NullReporter"]
