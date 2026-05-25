"""skills.lock — deterministic install lockfile for Bulbasaur projects.

Format (YAML, v1 per ADR 0011):

    lockfile_version: 1
    marketplaces:
      - ref: ./my-team-marketplace
        resolved_commit: abc123...   # when Git-backed; omitted for filesystem refs
    plugins:
      - name: my-skill
        version: 0.1.0
        strictness: team
        digest: sha256:...           # SHA-256 of the plugin bundle
        source: ./my-team-marketplace#my-skill@0.1.0

`bbsctl install` is deterministic given lock + marketplace refs.
`bbsctl lock` regenerates the file.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

_LOCKFILE_NAME = "skills.lock"
_LOCKFILE_VERSION = 1


@dataclass
class LockMarketplace:
    ref: str
    resolved_commit: str | None = None


@dataclass
class LockPlugin:
    name: str
    version: str
    strictness: str
    digest: str          # sha256:<hex>
    source: str          # <marketplace-ref>#<name>@<version>


@dataclass
class LockFile:
    """In-memory representation of skills.lock."""

    version: int = _LOCKFILE_VERSION
    marketplaces: list[LockMarketplace] = field(default_factory=list)
    plugins: list[LockPlugin] = field(default_factory=list)

    # Path to the file that was loaded (None if constructed in memory).
    source_path: Path | None = None

    def add_or_update_plugin(self, plugin: LockPlugin) -> None:
        """Upsert a plugin entry by name."""
        for i, existing in enumerate(self.plugins):
            if existing.name == plugin.name:
                self.plugins[i] = plugin
                return
        self.plugins.append(plugin)

    def remove_plugin(self, name: str) -> bool:
        before = len(self.plugins)
        self.plugins = [p for p in self.plugins if p.name != name]
        return len(self.plugins) < before

    def get_plugin(self, name: str) -> LockPlugin | None:
        for p in self.plugins:
            if p.name == name:
                return p
        return None

    def has_marketplace(self, ref: str) -> bool:
        return any(m.ref == ref for m in self.marketplaces)

    def add_marketplace(self, ref: str, *, resolved_commit: str | None = None) -> None:
        if not self.has_marketplace(ref):
            self.marketplaces.append(
                LockMarketplace(ref=ref, resolved_commit=resolved_commit)
            )


def load_lock(project_dir: Path) -> LockFile:
    """Load skills.lock from `project_dir`. Returns an empty LockFile if absent."""
    path = project_dir / _LOCKFILE_NAME
    if not path.exists():
        return LockFile()

    yaml = YAML(typ="safe")
    raw = yaml.load(path)
    if not isinstance(raw, dict):
        return LockFile()

    version = int(raw.get("lockfile_version", 1))
    marketplaces = [
        LockMarketplace(
            ref=m.get("ref", ""),
            resolved_commit=m.get("resolved_commit"),
        )
        for m in (raw.get("marketplaces") or [])
        if isinstance(m, dict)
    ]
    plugins = [
        LockPlugin(
            name=p.get("name", ""),
            version=p.get("version", "0.0.0"),
            strictness=p.get("strictness", "local"),
            digest=p.get("digest", ""),
            source=p.get("source", ""),
        )
        for p in (raw.get("plugins") or [])
        if isinstance(p, dict)
    ]
    return LockFile(
        version=version,
        marketplaces=marketplaces,
        plugins=plugins,
        source_path=path,
    )


def write_lock(lock: LockFile, project_dir: Path) -> Path:
    """Write skills.lock to `project_dir`. Returns the path written."""
    data = {
        "lockfile_version": lock.version,
        "marketplaces": [
            {k: v for k, v in {"ref": m.ref, "resolved_commit": m.resolved_commit}.items() if v}
            for m in lock.marketplaces
        ],
        "plugins": [
            {
                "name": p.name,
                "version": p.version,
                "strictness": p.strictness,
                "digest": p.digest,
                "source": p.source,
            }
            for p in sorted(lock.plugins, key=lambda x: x.name)
        ],
    }
    path = project_dir / _LOCKFILE_NAME
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 4096
    with path.open("w", encoding="utf-8") as fh:
        fh.write(
            "# Bulbasaur skills lockfile — do not edit manually. "
            "Regenerate with `bbsctl lock`.\n"
        )
        yaml.dump(data, fh)
    return path


def digest_plugin_dir(plugin_dir: Path) -> str:
    """Compute a SHA-256 digest of a plugin directory's stable files.

    Hashes the content of SKILL.md, skill.yaml, and plugin.json (if present)
    in deterministic order. Suitable for lockfile integrity checks.
    """
    h = hashlib.sha256()
    for fname in sorted(["SKILL.md", "skill.yaml", ".claude-plugin/plugin.json"]):
        p = plugin_dir / fname
        if p.exists():
            h.update(fname.encode())
            h.update(p.read_bytes())
    return f"sha256:{h.hexdigest()}"


__all__ = [
    "LockFile",
    "LockMarketplace",
    "LockPlugin",
    "digest_plugin_dir",
    "load_lock",
    "write_lock",
]
