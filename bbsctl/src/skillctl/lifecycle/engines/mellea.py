"""Mellea skills compiler adapter — compile → certify; collect audit/."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from skillctl.lifecycle.config import MELLEA_INSTALL, MELLEA_PIN
from skillctl.lifecycle.engines.base import StageContext
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.result import EngineInfo, StageResult, StageStatus
from skillctl.strictness import Strictness

_AUDIT_FILES = (
    "CERTIFICATION.md",
    "POLICY.md",
    "policy_manifest.json",
    "audit_trail.jsonl",
    "pipeline_report.json",
)
_DETAIL_LIMIT = 500
_COMPILE_TIMEOUT_S = 1800
_CERTIFY_TIMEOUT_S = 3600


class MelleaEngine:
    name = "mellea"

    def available(self) -> bool:
        return shutil.which("mellea-skills") is not None

    def version(self) -> str:
        return MELLEA_PIN

    def install_fix(self) -> str:
        return MELLEA_INSTALL

    def resolved_model_ids(self, ctx: StageContext) -> dict[str, str]:
        # Tags can drift; adapters should resolve digests when possible.
        # Until Ollama/vLLM resolution lands, record the configured tags.
        return {
            "risk_model": ctx.config.mellea.risk_model,
            "guardian_model": ctx.config.mellea.guardian_model,
            "inference_engine": ctx.config.mellea.inference_engine,
        }

    def run(self, ctx: StageContext) -> StageResult:
        if not self.available():
            return self._error("mellea-skills not on PATH")

        compile_proc = _run(
            ["mellea-skills", "compile", str(ctx.skill_dir)],
            timeout=_COMPILE_TIMEOUT_S,
        )
        if compile_proc.returncode != 0:
            return self._error(_proc_detail(compile_proc))

        compiled = find_compiled_dir(ctx.skill_dir)
        if compiled is None:
            return self._error(
                "mellea-skills compile succeeded but no <name>_mellea dir found"
            )

        cfg = ctx.config.mellea
        cmd = [
            "mellea-skills",
            "certify",
            str(compiled),
            "--n_fixtures",
            str(cfg.n_fixtures),
            "--inference-engine",
            cfg.inference_engine,
            "--risk-model",
            cfg.risk_model,
            "--guardian-model",
            cfg.guardian_model,
        ]
        if ctx.strictness.includes(Strictness.REGULATED):
            cmd.append("--enforce")

        certify_proc = _run(cmd, timeout=_CERTIFY_TIMEOUT_S)
        artifacts = collect_audit(compiled, ctx.skill_dir)
        if certify_proc.returncode != 0:
            return StageResult(
                stage=Stage.CERTIFY.value,
                status=StageStatus.FAILED,
                engine=self._info(),
                artifacts=artifacts,
                detail=_proc_detail(certify_proc),
            )

        return StageResult(
            stage=Stage.CERTIFY.value,
            status=StageStatus.PASSED,
            engine=self._info(),
            artifacts=artifacts,
            detail="certify ok",
        )

    def _error(self, detail: str) -> StageResult:
        return StageResult(
            stage=Stage.CERTIFY.value,
            status=StageStatus.ERROR,
            engine=self._info(),
            detail=detail,
        )

    def _info(self) -> EngineInfo:
        return EngineInfo(name=self.name, version=self.version(), revision=MELLEA_PIN)


def find_compiled_dir(skill_dir: Path) -> Path | None:
    """Locate the `*_mellea` tree produced by `mellea-skills compile`."""
    sibling = skill_dir.parent / f"{skill_dir.name}_mellea"
    if sibling.is_dir():
        return sibling
    nested = skill_dir / f"{skill_dir.name}_mellea"
    if nested.is_dir():
        return nested
    for cand in sorted(skill_dir.parent.glob("*_mellea")):
        if cand.is_dir():
            return cand
    return None


def collect_audit(compiled: Path, skill_dir: Path) -> dict[str, str]:
    """Copy known audit artifacts into `skill_dir/dist/certification/`."""
    audit = compiled / "audit"
    if not audit.is_dir():
        audit = compiled.parent / "audit"
    dest_root = skill_dir / "dist" / "certification"
    dest_root.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    if not audit.is_dir():
        return artifacts
    for name in _AUDIT_FILES:
        src = audit / name
        if src.is_file():
            dest = dest_root / name
            shutil.copy2(src, dest)
            artifacts[f"certification/{name}"] = str(dest)
    return artifacts


def _run(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _proc_detail(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stderr or proc.stdout or "")[:_DETAIL_LIMIT]


__all__ = ["MelleaEngine", "collect_audit", "find_compiled_dir"]
