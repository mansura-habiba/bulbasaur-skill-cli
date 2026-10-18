"""Langflow component that runs bbsctl compile|validate|eval via subprocess."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

EvalStage = Literal["compile", "validate", "eval"]


@dataclass(frozen=True)
class SkillEvalRequest:
    skill_dir: Path
    stage: EvalStage
    timeout_sec: float


@dataclass(frozen=True)
class SkillEvalOutcome:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    report: dict | None


def _resolve_bbsctl() -> list[str]:
    """Prefer the public `bbsctl` binary; fall back to `python -m skillctl`."""
    bbsctl = shutil.which("bbsctl")
    if bbsctl:
        return [bbsctl]
    return ["python", "-m", "skillctl"]


def _parse_report(stdout: str) -> dict | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def run_skill_eval(req: SkillEvalRequest) -> SkillEvalOutcome:
    skill_dir = Path(req.skill_dir).expanduser().resolve()
    if req.stage not in ("compile", "validate", "eval"):
        raise ValueError(f"unsupported stage: {req.stage!r}")
    cmd = [*_resolve_bbsctl(), req.stage, str(skill_dir)]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=req.timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return SkillEvalOutcome(
            ok=False,
            exit_code=124,
            stdout=stdout,
            stderr=stderr or f"timed out after {req.timeout_sec}s",
            report=None,
        )
    except FileNotFoundError as exc:
        return SkillEvalOutcome(
            ok=False,
            exit_code=127,
            stdout="",
            stderr=str(exc),
            report=None,
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return SkillEvalOutcome(
        ok=completed.returncode == 0,
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        report=_parse_report(stdout),
    )


def _import_lfx() -> tuple[type, Any]:
    """Load Component and Message from Langflow when present; else local stubs."""
    try:
        from lfx.custom import Component as LfxComponent  # type: ignore[import-not-found]
        from lfx.schema import Message as LfxMessage  # type: ignore[import-not-found]

        return LfxComponent, LfxMessage
    except ImportError:
        pass
    try:
        from langflow.custom import Component as LfxComponent  # type: ignore[import-not-found]
        from langflow.schema import Message as LfxMessage  # type: ignore[import-not-found]

        return LfxComponent, LfxMessage
    except ImportError:
        pass

    class LfxComponent:
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class LfxMessage:
        def __init__(self, text: str = "", **kwargs: Any) -> None:
            self.text = text
            self.data = kwargs

    return LfxComponent, LfxMessage


Component, Message = _import_lfx()


class BbsctlSkillEvalComponent(Component):
    display_name = "bbsctl Skill Eval"
    description = "Run bbsctl compile, validate, or eval on a skill directory."
    icon = "terminal"
    name = "BbsctlSkillEval"

    inputs: list[Any] = []
    outputs: list[Any] = []

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.skill_dir: str = kwargs.get("skill_dir", getattr(self, "skill_dir", ""))
        self.stage: EvalStage = kwargs.get("stage", getattr(self, "stage", "compile"))
        self.timeout_sec: float = float(
            kwargs.get("timeout_sec", getattr(self, "timeout_sec", 120.0))
        )
        self._outcome: SkillEvalOutcome | None = None

    def build_request(self) -> SkillEvalRequest:
        return SkillEvalRequest(
            skill_dir=Path(self.skill_dir),
            stage=self.stage,  # type: ignore[arg-type]
            timeout_sec=float(self.timeout_sec),
        )

    def evaluate(self) -> SkillEvalOutcome:
        if self._outcome is None:
            self._outcome = run_skill_eval(self.build_request())
        return self._outcome

    def pass_result(self) -> Any:
        outcome = self.evaluate()
        if not outcome.ok:
            return None
        body = outcome.stdout.strip() or json.dumps(
            {"ok": True, "exit_code": outcome.exit_code, "report": outcome.report}
        )
        return Message(text=body)

    def fail_result(self) -> Any:
        outcome = self.evaluate()
        if outcome.ok:
            return None
        detail = outcome.stderr.strip() or outcome.stdout.strip() or f"exit {outcome.exit_code}"
        return Message(text=detail)
