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
        digest: sha256:...           # SHA-256 over every shipped file (digest_plugin_dir)
        source: ./my-team-marketplace#my-skill@0.1.0

`bbsctl install` is deterministic given lock + marketplace refs.
`bbsctl lock` regenerates the file.
"""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from .bundle import _sha256_file, _walk

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
    """Compute a SHA-256 digest of every file a plugin directory ships.

    Walks the same files as `bundle.lock` (skipping the lock, the signature,
    and cruft such as `.git/`), so a change to any skill file, script, or
    executable bit changes the digest. The digest is the SHA-256 of one line
    per file, sorted by path in byte order:

        <sha256 of file> <x if owner-executable, else -> <posix path>\\n
    """
    entries: list[tuple[bytes, str]] = []
    for path in _walk(plugin_dir):
        rel = path.relative_to(plugin_dir).as_posix()
        mode = "x" if path.stat().st_mode & stat.S_IXUSR else "-"
        entries.append((rel.encode("utf-8"), f"{_sha256_file(path)} {mode} {rel}\n"))
    h = hashlib.sha256()
    for _, line in sorted(entries):
        h.update(line.encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


__all__ = [
    "LockFile",
    "LockMarketplace",
    "LockPlugin",
    "digest_plugin_dir",
    "load_lock",
    "write_lock",
]
