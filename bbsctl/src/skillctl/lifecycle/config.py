"""Load `[tool.bbsctl]` lifecycle settings from the nearest pyproject.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from skillctl.strictness import Strictness

# Pinned SHAs for doctor / evidence (M0 pins, 2026-10-18).
SKILLSPECTOR_PIN = "cf5cac7ba5c756a6e0ebf52dc9763f49422f889f"
MELLEA_PIN = "1538a0870ab9868ff5252c96722ba3827a4345ab"

SKILLSPECTOR_INSTALL = (
    f'uv tool install "git+https://github.com/NVIDIA/SkillSpector@{SKILLSPECTOR_PIN}"'
)
MELLEA_INSTALL = (
    f'uv tool install '
    f'"git+https://github.com/generative-computing/mellea-skills-compiler@{MELLEA_PIN}"'
)


@dataclass
class MelleaEngineConfig:
    inference_engine: str = "ollama"
    risk_model: str = "granite4.1:3b"
    guardian_model: str = "ibm/granite3.3-guardian:8b"
    n_fixtures: int = 3


@dataclass
class LifecycleConfig:
    """Resolved bbsctl lifecycle / engine config from `[tool.bbsctl]`."""

    default_strictness: Strictness = Strictness.TEAM
    # Defaults favour the always-available fallback so `bbsctl pipeline`
    # works without external CLIs. Pin SkillSpector / Mellea in pyproject when ready.
    scan_engine: str = "bbsctl-audit"  # or skillspector
    certify_engine: str = "none"  # or mellea
    mellea: MelleaEngineConfig = field(default_factory=MelleaEngineConfig)
    source_path: Path | None = None


def load_lifecycle_config(start_dir: Path) -> LifecycleConfig:
    """Find `[tool.bbsctl]` walking up from start_dir."""
    pyproject = _find_pyproject(start_dir)
    if pyproject is None:
        return LifecycleConfig()

    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return LifecycleConfig(source_path=pyproject)

    raw = data.get("tool", {}).get("bbsctl", {})
    if not raw:
        return LifecycleConfig(source_path=pyproject)

    engines = raw.get("engines", {})
    mellea_raw = engines.get("mellea", {}) if isinstance(engines, dict) else {}
    if not isinstance(mellea_raw, dict):
        mellea_raw = {}

    mellea = MelleaEngineConfig(
        inference_engine=str(mellea_raw.get("inference_engine", "ollama")),
        risk_model=str(mellea_raw.get("risk_model", "granite4.1:3b")),
        guardian_model=str(
            mellea_raw.get("guardian_model", "ibm/granite3.3-guardian:8b")
        ),
        n_fixtures=int(mellea_raw.get("n_fixtures", 3)),
    )

    return LifecycleConfig(
        default_strictness=Strictness.from_string(
            raw.get("default_strictness", "team")
        ),
        scan_engine=str(engines.get("scan", "bbsctl-audit")),
        certify_engine=str(engines.get("certify", "none")),
        mellea=mellea,
        source_path=pyproject,
    )


def _find_pyproject(start: Path) -> Path | None:
    candidate = start.resolve()
    for _ in range(20):
        p = candidate / "pyproject.toml"
        if p.exists():
            return p
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


__all__ = [
    "MELLEA_INSTALL",
    "MELLEA_PIN",
    "SKILLSPECTOR_INSTALL",
    "SKILLSPECTOR_PIN",
    "LifecycleConfig",
    "MelleaEngineConfig",
    "load_lifecycle_config",
]
