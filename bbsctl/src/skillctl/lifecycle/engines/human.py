"""Human approval stage — no automation can satisfy this."""

from __future__ import annotations

from skillctl.eval.reproducibility import compute_skill_hash
from skillctl.messaging import FrameworkError, emit
from skillctl.lifecycle.engines.base import StageContext
from skillctl.lifecycle.evidence import (
    evidence_dir_for,
    latest_evidence_bundle,
    verify_evidence,
    write_approval,
)
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.result import EngineInfo, StageResult, StageStatus


class HumanEngine:
    name = "human"

    def available(self) -> bool:
        return True

    def version(self) -> str:
        return "1"

    def install_fix(self) -> str:
        return "Human approval requires `bbsctl approve --by <id>`."

    def run(self, ctx: StageContext) -> StageResult:
        skill_hash = compute_skill_hash(ctx.skill_dir)
        bundle = evidence_dir_for(ctx.skill_dir, skill_hash)
        if not (bundle / "manifest.json").exists():
            bundle = latest_evidence_bundle(ctx.skill_dir)

        if ctx.approve_by:
            if bundle is None or not (bundle / "manifest.json").exists():
                emit(
                    FrameworkError(
                        summary="no evidence bundle to approve",
                        detail="run pipeline stages before approve",
                        fix="Run `bbsctl pipeline --to certify` then `bbsctl approve --by <id>`.",
                        docs="../docs/lifecycle.md",
                    )
                )
                return StageResult(
                    stage=Stage.APPROVE.value,
                    status=StageStatus.ERROR,
                    engine=EngineInfo(name=self.name, version="1"),
                    detail="no bundle",
                )
            path = write_approval(bundle, by=ctx.approve_by, note=ctx.approve_note)
            return StageResult(
                stage=Stage.APPROVE.value,
                status=StageStatus.PASSED,
                engine=EngineInfo(name=self.name, version="1"),
                artifacts={"approval.json": str(path)},
                detail=f"approved by {ctx.approve_by}",
            )

        if bundle is not None and (bundle / "approval.json").exists():
            ok, errors = verify_evidence(bundle, skill_dir=ctx.skill_dir)
            if ok:
                return StageResult(
                    stage=Stage.APPROVE.value,
                    status=StageStatus.PASSED,
                    engine=EngineInfo(name=self.name, version="1"),
                    artifacts={"approval.json": str(bundle / "approval.json")},
                    detail="existing approval valid",
                )
            return StageResult(
                stage=Stage.APPROVE.value,
                status=StageStatus.WAITING,
                engine=EngineInfo(name=self.name, version="1"),
                detail="; ".join(errors) or "approval stale",
            )

        return StageResult(
            stage=Stage.APPROVE.value,
            status=StageStatus.WAITING,
            engine=EngineInfo(name=self.name, version="1"),
            detail="waiting on `bbsctl approve --by <id>`",
        )


__all__ = ["HumanEngine"]
