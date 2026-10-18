"""Factory: stage → engine instance (config-driven)."""

from __future__ import annotations

from skillctl.messaging import FrameworkError
from skillctl.lifecycle.config import LifecycleConfig
from skillctl.lifecycle.engines.base import Engine
from skillctl.lifecycle.engines.bbsctl import BbsctlEngine
from skillctl.lifecycle.engines.bbsctl_audit import BbsctlAuditEngine
from skillctl.lifecycle.engines.human import HumanEngine
from skillctl.lifecycle.engines.mellea import MelleaEngine
from skillctl.lifecycle.engines.skillspector import SkillspectorEngine
from skillctl.lifecycle.pipeline import Stage

# Engines that have real adapters — vapor-options must only advertise these.
_ENGINE_NAMES = ("bbsctl", "skillspector", "bbsctl-audit", "mellea", "human", "none")


def list_engine_names() -> list[str]:
    return list(_ENGINE_NAMES)


def build_engines(config: LifecycleConfig) -> dict[Stage, Engine]:
    """Build the stage → engine map for a run."""
    bbsctl = BbsctlEngine()
    engines: dict[Stage, Engine] = {
        Stage.NEW: bbsctl,
        Stage.COMPILE: bbsctl,
        Stage.EVAL: bbsctl,
        Stage.PUBLISH: bbsctl,
        Stage.APPROVE: HumanEngine(),
    }

    scan_name = config.scan_engine
    if scan_name == "skillspector":
        engines[Stage.SCAN] = SkillspectorEngine()
    elif scan_name == "bbsctl-audit":
        engines[Stage.SCAN] = BbsctlAuditEngine()
    else:
        raise FrameworkError(
            summary=f"unknown scan engine `{scan_name}`",
            detail=f"known: skillspector, bbsctl-audit",
            fix='Set `[tool.bbsctl.engines] scan = "skillspector"` or `"bbsctl-audit"`.',
            docs="../docs/lifecycle.md",
        )

    certify_name = config.certify_engine
    if certify_name == "mellea":
        engines[Stage.CERTIFY] = MelleaEngine()
    elif certify_name == "none":
        engines[Stage.CERTIFY] = _NoneEngine(stage=Stage.CERTIFY)
    else:
        raise FrameworkError(
            summary=f"unknown certify engine `{certify_name}`",
            detail="known: mellea, none",
            fix='Set `[tool.bbsctl.engines] certify = "mellea"` or `"none"`.',
            docs="../docs/lifecycle.md",
        )

    return engines


class _NoneEngine:
    """Explicit no-op engine for stages disabled below org."""

    name = "none"

    def __init__(self, *, stage: Stage) -> None:
        self._stage = stage

    def available(self) -> bool:
        return False

    def version(self) -> str:
        return "none"

    def install_fix(self) -> str:
        if self._stage == Stage.CERTIFY:
            return (
                'Stage `certify` is disabled (`[tool.bbsctl.engines] certify = "none"`). '
                "Run `bbsctl mellea-certify`, or set `certify = \"mellea\"`."
            )
        return f"Stage `{self._stage.value}` is disabled in config."


    def run(self, ctx):  # type: ignore[no-untyped-def]
        from skillctl.lifecycle.result import EngineInfo, StageResult, StageStatus

        return StageResult(
            stage=self._stage.value,
            status=StageStatus.SKIPPED,
            engine=EngineInfo(name="none"),
            detail="engine=none",
        )


__all__ = ["build_engines", "list_engine_names"]
