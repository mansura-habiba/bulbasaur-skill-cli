"""SkillSpector subprocess adapter — SARIF → findings."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from skillctl.lifecycle.config import SKILLSPECTOR_INSTALL, SKILLSPECTOR_PIN
from skillctl.lifecycle.engines.base import StageContext
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.result import EngineInfo, Finding, StageResult, StageStatus
from skillctl.strictness import Strictness


class SkillspectorEngine:
    name = "skillspector"

    def available(self) -> bool:
        if sys.version_info < (3, 12):
            return False
        return shutil.which("skillspector") is not None

    def version(self) -> str:
        return SKILLSPECTOR_PIN

    def install_fix(self) -> str:
        if sys.version_info < (3, 12):
            return (
                "SkillSpector requires Python >= 3.12. "
                "Use a 3.12+ interpreter, or run legacy `bbsctl scan` "
                "(bbsctl-audit) instead of `bbsctl inspect`. "
                f"Install: {SKILLSPECTOR_INSTALL}"
            )
        return SKILLSPECTOR_INSTALL

    def run(self, ctx: StageContext) -> StageResult:
        if not self.available():
            return StageResult(
                stage=Stage.SCAN.value,
                status=StageStatus.ERROR,
                engine=self._info(),
                detail="skillspector not available",
            )

        out_dir = ctx.skill_dir / "dist"
        out_dir.mkdir(parents=True, exist_ok=True)
        sarif_path = out_dir / "scan.sarif"

        cmd = [
            "skillspector",
            "scan",
            str(ctx.skill_dir),
            "--format",
            "sarif",
            "--output",
            str(sarif_path),
            "--no-llm",
        ]
        if ctx.strictness.includes(Strictness.REGULATED):
            cmd.append("--fail-on-findings")

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return StageResult(
                stage=Stage.SCAN.value,
                status=StageStatus.ERROR,
                engine=self._info(),
                detail=str(exc),
            )

        findings = _parse_sarif(sarif_path) if sarif_path.is_file() else []
        artifacts = {"scan.sarif": str(sarif_path)} if sarif_path.is_file() else {}

        if proc.returncode == 0:
            status = StageStatus.PASSED
        elif proc.returncode == 1:
            status = StageStatus.FAILED
        else:
            status = StageStatus.ERROR

        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        return StageResult(
            stage=Stage.SCAN.value,
            status=status,
            findings=findings,
            artifacts=artifacts,
            engine=self._info(),
            detail=detail or f"exit={proc.returncode}",
        )

    def _info(self) -> EngineInfo:
        return EngineInfo(name=self.name, version=self.version(), revision=SKILLSPECTOR_PIN)


def _parse_sarif(path: Path) -> list[Finding]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    findings: list[Finding] = []
    for run in data.get("runs") or []:
        for result in run.get("results") or []:
            msg = ""
            message = result.get("message") or {}
            if isinstance(message, dict):
                msg = str(message.get("text") or "")
            else:
                msg = str(message)
            loc = ""
            locations = result.get("locations") or []
            if locations:
                phys = (locations[0].get("physicalLocation") or {}).get(
                    "artifactLocation"
                ) or {}
                loc = str(phys.get("uri") or "")
            findings.append(
                Finding(
                    severity=str(result.get("level") or "warning"),
                    message=msg,
                    rule_id=str(result.get("ruleId") or ""),
                    location=loc,
                )
            )
    return findings


__all__ = ["SkillspectorEngine"]
