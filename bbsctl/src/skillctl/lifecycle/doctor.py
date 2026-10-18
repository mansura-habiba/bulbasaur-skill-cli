"""Engine discovery, pin checks, and model-requirement reporting."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from skillctl.lifecycle.config import (
    MELLEA_INSTALL,
    MELLEA_PIN,
    SKILLSPECTOR_INSTALL,
    SKILLSPECTOR_PIN,
    LifecycleConfig,
    load_lifecycle_config,
)

_OLLAMA_PROBE_TIMEOUT_S = 3


@dataclass
class ModelRequirement:
    """One model tag an engine expects (from config or CLI defaults)."""

    key: str
    value: str
    ready: bool | None = None  # None = could not probe
    fix: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EngineHealth:
    name: str
    found: bool
    version: str = ""
    pin: str = ""
    pin_match: bool | None = None  # None = unknown / not applicable
    note: str = ""
    fix: str = ""
    needs_llm: bool = False
    models: list[ModelRequirement] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "found": self.found,
            "version": self.version,
            "pin": self.pin,
            "pin_match": self.pin_match,
            "note": self.note,
            "fix": self.fix,
            "needs_llm": self.needs_llm,
            "models": [m.to_dict() for m in self.models],
        }


def check_engines(start_dir: Path | None = None) -> list[EngineHealth]:
    """Report availability of bbsctl / skillspector / mellea-skills + model needs."""
    config = load_lifecycle_config(start_dir or Path.cwd())
    return [
        _check_bbsctl(),
        _check_skillspector(),
        _check_mellea(config),
    ]


def format_doctor_report(rows: list[EngineHealth]) -> str:
    lines = ["bbsctl doctor", ""]
    for row in rows:
        status = "ok" if row.found else "MISSING"
        pin_bit = ""
        if row.pin:
            if row.pin_match is True:
                pin_bit = f"  pin=match ({row.pin[:12]}…)"
            elif row.pin_match is False:
                pin_bit = f"  pin=DRIFT (want {row.pin[:12]}…)"
            else:
                pin_bit = f"  pin={row.pin[:12]}…"
        ver = f"  {row.version}" if row.version else ""
        llm = "  needs_llm=yes" if row.needs_llm else "  needs_llm=no"
        lines.append(f"  [{status}] {row.name}{ver}{pin_bit}{llm}")
        if row.note:
            lines.append(f"         {row.note}")
        for model in row.models:
            ready = (
                "ready"
                if model.ready is True
                else "MISSING"
                if model.ready is False
                else "unprobed"
            )
            lines.append(f"         model {model.key}={model.value}  [{ready}]")
            if model.ready is False and model.fix:
                lines.append(f"         Fix: {model.fix}")
        if not row.found and row.fix:
            lines.append(f"         Fix: {row.fix}")
    return "\n".join(lines) + "\n"


def _check_bbsctl() -> EngineHealth:
    from skillctl import __version__

    return EngineHealth(
        name="bbsctl",
        found=True,
        version=__version__,
        note="in-process (same distribution)",
        needs_llm=False,
    )


def _check_skillspector() -> EngineHealth:
    row = _check_cli(
        name="skillspector",
        binary="skillspector",
        pin=SKILLSPECTOR_PIN,
        fix=SKILLSPECTOR_INSTALL,
        version_args=["--version"],
        python_min=(3, 12),
    )
    row.needs_llm = False
    row.note = (
        (row.note + "; " if row.note else "")
        + "bbsctl inspect always passes --no-llm (no model / API key)"
    )
    return row


def _check_mellea(config: LifecycleConfig) -> EngineHealth:
    row = _check_cli(
        name="mellea-skills",
        binary="mellea-skills",
        pin=MELLEA_PIN,
        fix=MELLEA_INSTALL,
        version_args=["--version"],
        python_min=None,
    )
    row.needs_llm = True
    cfg = config.mellea
    src = str(config.source_path) if config.source_path else "defaults"
    row.note = (
        (row.note + "; " if row.note else "")
        + f"models from [tool.bbsctl.engines.mellea] ({src})"
    )
    installed = _ollama_tags() if cfg.inference_engine == "ollama" else None
    if cfg.inference_engine == "ollama":
        engine_ready: bool | None = installed is not None
        engine_fix = (
            ""
            if engine_ready
            else "Install Ollama and ensure `ollama` is on PATH (`ollama serve`)"
        )
    else:
        engine_ready = None
        engine_fix = (
            f"Probe not implemented for inference_engine={cfg.inference_engine!r}; "
            "ensure that backend is running before mellea-certify"
        )
    row.models = [
        _model_req(
            "inference_engine",
            cfg.inference_engine,
            ready=engine_ready,
            fix=engine_fix,
        ),
        _model_req(
            "risk_model",
            cfg.risk_model,
            ready=_tag_ready(cfg.risk_model, installed),
            fix=f"ollama pull {cfg.risk_model}",
        ),
        _model_req(
            "guardian_model",
            cfg.guardian_model,
            ready=_tag_ready(cfg.guardian_model, installed),
            fix=f"ollama pull {cfg.guardian_model}",
        ),
    ]
    return row


def _model_req(
    key: str, value: str, *, ready: bool | None, fix: str
) -> ModelRequirement:
    return ModelRequirement(key=key, value=value, ready=ready, fix=fix if ready is False else "")


def _tag_ready(tag: str, installed: set[str] | None) -> bool | None:
    if installed is None:
        return None
    if tag in installed:
        return True
    # Ollama often lists "name:tag" and short "name"; accept either form.
    short = tag.split(":", 1)[0]
    if any(t == tag or t.startswith(short + ":") or t == short for t in installed):
        return True
    return False


def _ollama_tags() -> set[str] | None:
    """Best-effort local tag set. None when ollama is missing or unresponsive."""
    if shutil.which("ollama") is None:
        return None
    try:
        proc = subprocess.run(
            ["ollama", "list", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=_OLLAMA_PROBE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        # Older ollama may lack --format json; fall back to plain list.
        try:
            proc = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=_OLLAMA_PROBE_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        tags: set[str] = set()
        for line in (proc.stdout or "").splitlines()[1:]:
            parts = line.split()
            if parts:
                tags.add(parts[0])
        return tags
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    tags = set()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                tags.add(str(item["name"]))
            elif isinstance(item, str):
                tags.add(item)
    return tags


def _check_cli(
    *,
    name: str,
    binary: str,
    pin: str,
    fix: str,
    version_args: list[str],
    python_min: tuple[int, int] | None,
) -> EngineHealth:
    if python_min is not None and sys.version_info < python_min:
        return EngineHealth(
            name=name,
            found=False,
            pin=pin,
            note=(
                f"requires Python >={python_min[0]}.{python_min[1]} "
                f"(this interpreter is {sys.version_info.major}.{sys.version_info.minor})"
            ),
            fix=fix,
        )

    path = shutil.which(binary)
    if path is None:
        return EngineHealth(
            name=name,
            found=False,
            pin=pin,
            note="CLI not on PATH",
            fix=fix,
        )

    version = _run_version(path, version_args)
    pin_match = None
    if pin and version and pin[:12] in version:
        pin_match = True
    elif pin and version:
        pin_match = False

    return EngineHealth(
        name=name,
        found=True,
        version=version or path,
        pin=pin,
        pin_match=pin_match,
        note=str(Path(path)),
    )


def _run_version(binary: str, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    out = (proc.stdout or proc.stderr or "").strip()
    return out.splitlines()[0] if out else ""


__all__ = [
    "EngineHealth",
    "ModelRequirement",
    "check_engines",
    "format_doctor_report",
]
