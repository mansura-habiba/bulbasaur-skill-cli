"""In-process bbsctl engine for new / compile / eval / publish."""

from __future__ import annotations

import argparse
import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from skillctl import __version__
from skillctl.messaging import FrameworkError, emit
from skillctl.lifecycle.engines.base import StageContext
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.result import EngineInfo, Finding, StageResult, StageStatus
from skillctl.strictness import Strictness


class BbsctlEngine:
    """Delegates to skillctl.commands.* without spawning a subprocess."""

    name = "bbsctl"

    def available(self) -> bool:
        return True

    def version(self) -> str:
        return __version__

    def install_fix(self) -> str:
        return "bbsctl is part of this package — reinstall with `uv pip install -e bbsctl`."

    def run(self, ctx: StageContext) -> StageResult:
        if ctx.stage == Stage.NEW:
            return self._new(ctx)
        if ctx.stage == Stage.COMPILE:
            return self._compile(ctx)
        if ctx.stage == Stage.EVAL:
            return self._eval(ctx)
        if ctx.stage == Stage.PUBLISH:
            return self._publish(ctx)
        return StageResult(
            stage=ctx.stage.value,
            status=StageStatus.ERROR,
            engine=self._info(),
            detail=f"bbsctl engine does not handle stage `{ctx.stage.value}`",
        )

    def _info(self) -> EngineInfo:
        return EngineInfo(name=self.name, version=self.version(), revision=self.version())

    def _new(self, ctx: StageContext) -> StageResult:
        from skillctl.commands import new as new_cmd

        if not ctx.name:
            return StageResult(
                stage=Stage.NEW.value,
                status=StageStatus.ERROR,
                engine=self._info(),
                detail="skill name required for `new`",
            )
        args = argparse.Namespace(
            name=ctx.name,
            strictness=ctx.strictness.value,
            dir=str(ctx.skill_dir),
        )
        code = new_cmd.run(args)
        return StageResult(
            stage=Stage.NEW.value,
            status=StageStatus.PASSED if code == 0 else StageStatus.FAILED,
            engine=self._info(),
            detail=f"exit={code}",
        )

    def _compile(self, ctx: StageContext) -> StageResult:
        from skillctl.commands import compile as compile_cmd
        from skillctl.commands import validate as validate_cmd

        args = argparse.Namespace(
            skill_dir=str(ctx.skill_dir),
            strictness=ctx.strictness.value,
            output="silent",
        )
        code = compile_cmd.run(args)

        artifacts: dict[str, str] = {}
        report = ctx.skill_dir / "dist" / "compile-report.json"
        if report.is_file():
            artifacts["compile.json"] = str(report)

        # team+ always validates; --fast (pre-commit) also validates.
        need_validate = ctx.fast or ctx.strictness.includes(Strictness.TEAM)
        if code == 0 and need_validate:
            vargs = argparse.Namespace(
                skill_dir=str(ctx.skill_dir),
                fast=True,
                full=False,
                strictness=ctx.strictness.value,
                output="silent",
            )
            vcode = validate_cmd.run(vargs)
            if vcode != 0:
                return StageResult(
                    stage=Stage.COMPILE.value,
                    status=StageStatus.FAILED,
                    engine=self._info(),
                    artifacts=artifacts,
                    findings=[
                        Finding(
                            severity="error",
                            message="validate --fast failed after compile",
                            rule_id="bbsctl.validate",
                        )
                    ],
                    detail=f"validate exit={vcode}",
                )

        return StageResult(
            stage=Stage.COMPILE.value,
            status=StageStatus.PASSED if code == 0 else StageStatus.FAILED,
            engine=self._info(),
            artifacts=artifacts,
            detail=f"compile exit={code}",
        )

    def _eval(self, ctx: StageContext) -> StageResult:
        from skillctl.commands import eval_cmd

        evals = ctx.skill_dir / "evals"
        if not evals.is_dir() or not any(evals.glob("*.json")):
            return StageResult(
                stage=Stage.EVAL.value,
                status=StageStatus.SKIPPED,
                engine=self._info(),
                detail="no evals/*.json corpus",
            )

        buf = io.StringIO()
        with redirect_stdout(buf):
            args = argparse.Namespace(
                skill_dir=str(ctx.skill_dir),
                mode="fast",
                suite=None,
                case=None,
                runtime=None,
                runtime_model=None,
                judge=None,
                judge_backend=None,
                judge_model=None,
                judge_threshold=None,
                judge_max_tokens=None,
                threshold=None,
                runtime_max_tokens=None,
                runtime_temperature=None,
                fuzz_n_variants=None,
                cache=ctx.use_cache,
                refresh_cache=False,
                snapshot=None,
                strictness=ctx.strictness.value,
                output="json",
            )
            code = eval_cmd.run(args)

        artifacts: dict[str, str] = {}
        out_path = ctx.skill_dir / "dist" / "eval.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        text = buf.getvalue().strip()
        if text:
            out_path.write_text(text + "\n", encoding="utf-8")
            artifacts["eval.json"] = str(out_path)

        findings: list[Finding] = []
        if code != 0 and text:
            try:
                data = json.loads(text)
                findings.append(
                    Finding(
                        severity="error",
                        message=(
                            f"eval score={data.get('score')} "
                            f"({data.get('passed_cases')}/{data.get('total_cases')})"
                        ),
                        rule_id="bbsctl.eval",
                    )
                )
            except json.JSONDecodeError:
                pass

        return StageResult(
            stage=Stage.EVAL.value,
            status=StageStatus.PASSED if code == 0 else StageStatus.FAILED,
            engine=self._info(),
            artifacts=artifacts,
            findings=findings,
            detail=f"eval exit={code}",
        )

    def _publish(self, ctx: StageContext) -> StageResult:
        from skillctl.commands import publish as publish_cmd
        from skillctl.lifecycle.evidence import latest_evidence_bundle, verify_evidence

        bundle = latest_evidence_bundle(ctx.skill_dir)
        if bundle is None:
            emit(
                FrameworkError(
                    summary="publish refused: no evidence bundle",
                    detail=f"looked under {ctx.skill_dir / '.bbsctl' / 'evidence'}",
                    fix="Run `bbsctl pipeline` through approve, then retry publish.",
                    docs="../docs/lifecycle.md",
                )
            )
            return StageResult(
                stage=Stage.PUBLISH.value,
                status=StageStatus.FAILED,
                engine=self._info(),
                detail="no evidence bundle",
            )

        ok, errors = verify_evidence(bundle, skill_dir=ctx.skill_dir)
        if not ok:
            emit(
                FrameworkError(
                    summary="publish refused: evidence bundle failed verification",
                    detail="; ".join(errors),
                    fix=(
                        "Re-run `bbsctl pipeline`, re-approve if SKILL.md changed, "
                        "then `bbsctl verify` before publish."
                    ),
                    docs="../docs/lifecycle.md",
                )
            )
            return StageResult(
                stage=Stage.PUBLISH.value,
                status=StageStatus.FAILED,
                engine=self._info(),
                findings=[Finding(severity="error", message=e) for e in errors],
                detail="verify failed",
            )

        args = argparse.Namespace(
            skill_dir=str(ctx.skill_dir),
            target="claude-code-local",
            output=None,
            marketplace=ctx.marketplace,
            option=[],
            strictness=ctx.strictness.value,
        )
        code = publish_cmd.run(args)

        if code == 0 and ctx.marketplace:
            plugin_root = Path(ctx.marketplace) / "plugins"
            if plugin_root.is_dir():
                dest = plugin_root / f"{ctx.skill_dir.name}-evidence"
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(bundle, dest)

        return StageResult(
            stage=Stage.PUBLISH.value,
            status=StageStatus.PASSED if code == 0 else StageStatus.FAILED,
            engine=self._info(),
            detail=f"publish exit={code}",
        )


__all__ = ["BbsctlEngine"]
