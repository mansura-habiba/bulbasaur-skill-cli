"""Bundled reference policies — discover and load.

`bbsctl policy list` enumerates the catalog. Each entry is a YAML file
shipped with the wheel; callers reference catalog policies by short name
(e.g. `hipaa-baseline`) instead of a filesystem path.
"""

from __future__ import annotations

from pathlib import Path

_CATALOG_DIR = Path(__file__).parent


def catalog_dir() -> Path:
    """Return the catalog directory containing bundled policy YAML files."""
    return _CATALOG_DIR


def list_catalog_names() -> list[str]:
    """Return the short names (filenames without extension) of bundled policies."""
    return sorted(p.stem for p in _CATALOG_DIR.glob("*.yaml"))


def resolve_catalog_path(name: str) -> Path | None:
    """Resolve a short name to a catalog YAML path; None if not present."""
    candidate = _CATALOG_DIR / f"{name}.yaml"
    return candidate if candidate.is_file() else None


__all__ = ["catalog_dir", "list_catalog_names", "resolve_catalog_path"]
