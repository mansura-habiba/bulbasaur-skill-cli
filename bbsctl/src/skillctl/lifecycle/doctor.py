"""Engine discovery + pin checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from skillctl.lifecycle.config import (
    MELLEA_INSTALL,
    MELLEA_PIN,
    SKILLSPECTOR_INSTALL,
    SKILLSPECTOR_PIN,
)


@dataclass
class EngineHealth:
    name: str
    found: bool
    version: str = ""
    pin: str = ""
    pin_match: bool | None = None  # None = unknown / not applicable
    note: str = ""
    fix: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "found": self.found,
            "version": self.version,
            "pin": self.pin,
            "pin_match": self.pin_match,
            "note": self.note,
            "fix": self.fix,
        }


def check_engines() -> list[EngineHealth]:
    """Report availability of bbsctl / skillspector / mellea-skills."""
    return [
        _check_bbsctl(),
        _check_cli(
            name="skillspector",
            binary="skillspector",
            pin=SKILLSPECTOR_PIN,
            fix=SKILLSPECTOR_INSTALL,
            version_args=["--version"],
            python_min=(3, 12),
        ),
        _check_cli(
            name="mellea-skills",
            binary="mellea-skills",
            pin=MELLEA_PIN,
            fix=MELLEA_INSTALL,
            version_args=["--version"],
            python_min=None,
        ),
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
        lines.append(f"  [{status}] {row.name}{ver}{pin_bit}")
        if row.note:
            lines.append(f"         {row.note}")
        if not row.found and row.fix:
            lines.append(f"         Fix: {row.fix}")
    return "\n".join(lines) + "\n"


def _check_bbsctl() -> EngineHealth:
    # In-process: always available when lifecycle is installed from the same wheel.
    from skillctl import __version__

    return EngineHealth(
        name="bbsctl",
        found=True,
        version=__version__,
        note="in-process (same distribution)",
    )


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
        pin_match = False  # version string present but pin not visible — soft drift

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


__all__ = ["EngineHealth", "check_engines", "format_doctor_report"]
