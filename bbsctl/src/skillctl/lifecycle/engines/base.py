"""Engine protocol + stage context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from skillctl.lifecycle.config import LifecycleConfig
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.result import StageResult
from skillctl.strictness import Strictness


@dataclass
class StageContext:
    skill_dir: Path
    stage: Stage
    strictness: Strictness
    config: LifecycleConfig
    use_cache: bool = True
    # Optional kwargs for stage-specific commands
    name: str | None = None  # for `new`
    approve_by: str | None = None
    approve_note: str = ""
    marketplace: str | None = None
    fast: bool = False


@runtime_checkable
class Engine(Protocol):
    name: str

    def available(self) -> bool: ...

    def version(self) -> str: ...

    def install_fix(self) -> str: ...

    def run(self, ctx: StageContext) -> StageResult: ...


__all__ = ["Engine", "StageContext"]
