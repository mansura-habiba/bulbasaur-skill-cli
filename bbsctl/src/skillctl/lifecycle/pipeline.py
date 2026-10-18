"""Stage enum, strictness → StagePlan, fail-fast Runner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from skillctl.messaging import FrameworkError
from skillctl.lifecycle.result import StageResult, StageStatus
from skillctl.strictness import Strictness

if TYPE_CHECKING:
    from skillctl.lifecycle.config import LifecycleConfig
    from skillctl.lifecycle.engines.base import Engine, StageContext


class Stage(StrEnum):
    NEW = "new"
    COMPILE = "compile"
    SCAN = "scan"
    EVAL = "eval"
    CERTIFY = "certify"
    APPROVE = "approve"
    PUBLISH = "publish"


# Canonical pipeline order.
STAGE_ORDER: tuple[Stage, ...] = (
    Stage.NEW,
    Stage.COMPILE,
    Stage.SCAN,
    Stage.EVAL,
    Stage.CERTIFY,
    Stage.APPROVE,
    Stage.PUBLISH,
)


@dataclass(frozen=True)
class StageRequirement:
    stage: Stage
    required: bool  # False = optional (run if engine present, else warn+skip)


@dataclass
class StagePlan:
    """Ordered stages for a strictness level."""

    strictness: Strictness
    stages: list[StageRequirement] = field(default_factory=list)

    def stage_names(self) -> list[str]:
        return [s.stage.value for s in self.stages]


def plan_for_strictness(strictness: Strictness) -> StagePlan:
    """Map strictness → required/optional stages (docs/lifecycle.md)."""
    # compile always required for run (new is opt-in via explicit command)
    stages: list[StageRequirement] = [
        StageRequirement(Stage.COMPILE, required=True),
    ]

    if strictness == Strictness.LOCAL:
        stages.extend(
            [
                StageRequirement(Stage.SCAN, required=False),
                StageRequirement(Stage.EVAL, required=False),
            ]
        )
    elif strictness == Strictness.TEAM:
        stages.extend(
            [
                StageRequirement(Stage.SCAN, required=True),
                StageRequirement(Stage.EVAL, required=False),  # required if corpus exists — handled in runner
                StageRequirement(Stage.CERTIFY, required=False),
            ]
        )
    elif strictness == Strictness.ORG:
        stages.extend(
            [
                StageRequirement(Stage.SCAN, required=True),
                StageRequirement(Stage.EVAL, required=True),
                StageRequirement(Stage.CERTIFY, required=True),
                StageRequirement(Stage.APPROVE, required=True),
            ]
        )
    else:  # REGULATED
        stages.extend(
            [
                StageRequirement(Stage.SCAN, required=True),
                StageRequirement(Stage.EVAL, required=True),
                StageRequirement(Stage.CERTIFY, required=True),
                StageRequirement(Stage.APPROVE, required=True),
                StageRequirement(Stage.PUBLISH, required=False),  # explicit publish command
            ]
        )

    return StagePlan(strictness=strictness, stages=stages)


@dataclass
class RunReport:
    results: list[StageResult] = field(default_factory=list)
    exit_code: int = 0

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "exit_code": self.exit_code,
        }


class Runner:
    """Walk stages in order; fail fast; honour --from/--to/--skip."""

    def __init__(
        self,
        *,
        skill_dir: Path,
        config: LifecycleConfig,
        engines: dict[Stage, Engine],
        use_cache: bool = True,
        fast: bool = False,
        marketplace: str | None = None,
    ) -> None:
        self.skill_dir = skill_dir
        self.config = config
        self.engines = engines
        self.use_cache = use_cache
        self.fast = fast
        self.marketplace = marketplace

    def run(
        self,
        plan: StagePlan,
        *,
        from_stage: Stage | None = None,
        to_stage: Stage | None = None,
        skip: set[Stage] | None = None,
    ) -> RunReport:
        from skillctl.lifecycle.cache import StageCache
        from skillctl.lifecycle.engines.base import StageContext

        skip = skip or set()
        cache = StageCache() if self.use_cache else None
        results: list[StageResult] = []

        selected = self._slice(plan, from_stage=from_stage, to_stage=to_stage)

        for req in selected:
            if req.stage in skip:
                if req.required:
                    raise FrameworkError(
                        summary=f"cannot --skip required stage `{req.stage.value}`",
                        detail=f"strictness `{plan.strictness.value}` requires this stage",
                        fix=(
                            "Remove it from `--skip`, or lower strictness. "
                            "Optional stages may be skipped; required ones may not."
                        ),
                        docs="../docs/lifecycle.md",
                    )
                results.append(
                    StageResult(
                        stage=req.stage.value,
                        status=StageStatus.SKIPPED,
                        detail="skipped by --skip",
                    )
                )
                continue

            # team: eval becomes required when corpus exists
            required = req.required
            if (
                req.stage == Stage.EVAL
                and plan.strictness == Strictness.TEAM
                and (self.skill_dir / "evals").is_dir()
                and any((self.skill_dir / "evals").glob("*.json"))
            ):
                required = True

            engine = self.engines.get(req.stage)
            if engine is None or not engine.available():
                if required:
                    install = (
                        engine.install_fix()
                        if engine is not None
                        else f"No engine registered for stage `{req.stage.value}`."
                    )
                    fix = (
                        f"{install}\n"
                        f"{resume_fix(req.stage, skill_dir=self.skill_dir)}"
                    )
                    results.append(
                        StageResult(
                            stage=req.stage.value,
                            status=StageStatus.ERROR,
                            detail="engine missing",
                        )
                    )
                    raise FrameworkError(
                        summary=f"required engine missing for stage `{req.stage.value}`",
                        detail=f"strictness={plan.strictness.value}",
                        fix=fix,
                        docs="../docs/lifecycle.md",
                    )
                results.append(
                    StageResult(
                        stage=req.stage.value,
                        status=StageStatus.SKIPPED,
                        detail="optional engine not installed",
                    )
                )
                continue

            ctx = StageContext(
                skill_dir=self.skill_dir,
                stage=req.stage,
                strictness=plan.strictness,
                config=self.config,
                use_cache=self.use_cache,
                fast=self.fast,
                marketplace=self.marketplace,
            )

            if cache is not None:
                hit = cache.get(ctx, engine)
                if hit is not None:
                    hit.cached = True
                    results.append(hit)
                    if not hit.ok:
                        return RunReport(results=results, exit_code=self._exit_for(hit))
                    continue

            started = time.perf_counter()
            result = engine.run(ctx)
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            if cache is not None and result.ok:
                cache.put(ctx, engine, result)
            results.append(result)

            if result.status == StageStatus.WAITING:
                return RunReport(results=results, exit_code=3)
            if not result.ok:
                return RunReport(results=results, exit_code=self._exit_for(result))

        return RunReport(results=results, exit_code=0)

    @staticmethod
    def _exit_for(result: StageResult) -> int:
        if result.status == StageStatus.ERROR:
            return 2
        if result.status == StageStatus.WAITING:
            return 3
        return 1

    @staticmethod
    def _slice(
        plan: StagePlan,
        *,
        from_stage: Stage | None,
        to_stage: Stage | None,
    ) -> list[StageRequirement]:
        stages = list(plan.stages)
        if from_stage is not None:
            stages = [s for s in stages if _index(s.stage) >= _index(from_stage)]
        if to_stage is not None:
            stages = [s for s in stages if _index(s.stage) <= _index(to_stage)]
        return stages


def _index(stage: Stage) -> int:
    return STAGE_ORDER.index(stage)


def resume_fix(stage: Stage | str, *, skill_dir: Path | None = None) -> str:
    """Copy-pasteable resume hint after an engine/framework failure (exit 2)."""
    name = stage.value if isinstance(stage, Stage) else str(stage)
    path = ""
    if skill_dir is not None:
        try:
            rel = skill_dir.resolve().relative_to(Path.cwd())
            path = f" {rel}"
        except ValueError:
            path = f" {skill_dir}"
    return (
        f"After fixing the engine, resume with: "
        f"`bbsctl pipeline --from {name}{path}`. "
        "Earlier stages reuse the stage cache when the skill hash is unchanged."
    )


__all__ = [
    "STAGE_ORDER",
    "Runner",
    "RunReport",
    "Stage",
    "StagePlan",
    "StageRequirement",
    "plan_for_strictness",
    "resume_fix",
]
