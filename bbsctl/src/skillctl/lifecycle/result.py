"""Normalised stage outcome — engines adapt into this shape."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class StageStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    WAITING = "waiting"  # human approval pending


@dataclass
class Finding:
    """One normalised finding from any engine."""

    severity: str
    message: str
    rule_id: str = ""
    location: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EngineInfo:
    name: str
    version: str = ""
    revision: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageResult:
    """Common adapter output for every lifecycle stage."""

    stage: str
    status: StageStatus
    findings: list[Finding] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)  # name → path
    engine: EngineInfo = field(default_factory=lambda: EngineInfo(name="none"))
    duration_ms: int = 0
    cached: bool = False
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {StageStatus.PASSED, StageStatus.SKIPPED}

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status.value,
            "findings": [f.to_dict() for f in self.findings],
            "artifacts": dict(self.artifacts),
            "engine": self.engine.to_dict(),
            "duration_ms": self.duration_ms,
            "cached": self.cached,
            "detail": self.detail,
        }


__all__ = ["EngineInfo", "Finding", "StageResult", "StageStatus"]
