"""GitMarketplace — filesystem/Git-backed marketplace adapter (Phase 2).

Implements the registry contract for the team-tier MVP backend (ADR 0011):

    Directory layout on disk:
        <marketplace-dir>/
        ├── .claude-plugin/
        │   └── marketplace.json       # Claude Code plugin spec marketplace catalog
        └── plugins/
            └── <plugin-name>/
                ├── .claude-plugin/
                │   └── plugin.json
                └── skills/
                    └── <skill-name>/
                        ├── SKILL.md
                        └── skill.yaml   # if team+ strictness

`bbsctl marketplace init <path>` creates the skeleton.
`bbsctl publish --marketplace <path>` adds a plugin entry.
`bbsctl install` reads entries and copies into the consumer's cache.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from skillctl import __version__


@dataclass
class MarketplaceEntry:
    """One plugin entry in the marketplace catalog."""

    name: str
    source: str          # relative path from marketplace root
    description: str
    version: str
    strictness: str = "local"


@dataclass
class MarketplaceManifest:
    name: str
    owner: dict[str, str]
    description: str
    plugins: list[MarketplaceEntry] = field(default_factory=list)
    generated_by: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "owner": self.owner,
            "description": self.description,
            "plugins": [
                {
                    "name": e.name,
                    "source": e.source,
                    "description": e.description,
                    "version": e.version,
                    "strictness": e.strictness,
                }
                for e in self.plugins
            ],
            "metadata": {"generated_by": self.generated_by or f"skillctl {__version__}"},
        }

    @classmethod
    def from_dict(cls, data: dict) -> MarketplaceManifest:
        entries = [
            MarketplaceEntry(
                name=p.get("name", ""),
                source=p.get("source", ""),
                description=p.get("description", ""),
                version=p.get("version", "0.1.0"),
                strictness=p.get("strictness", "local"),
            )
            for p in data.get("plugins", [])
        ]
        return cls(
            name=data.get("name", ""),
            owner=data.get("owner", {"name": "unknown"}),
            description=data.get("description", ""),
            plugins=entries,
            generated_by=data.get("metadata", {}).get("generated_by", ""),
        )


class MarketplaceNotFoundError(Exception):
    pass


class GitMarketplace:
    """Filesystem/Git-backed marketplace adapter.

    Operates against a directory that has been initialised by
    `bbsctl marketplace init <path>` (i.e. contains `.claude-plugin/marketplace.json`).
    """

    _MARKETPLACE_JSON = Path(".claude-plugin") / "marketplace.json"
    _PLUGINS_DIR = Path("plugins")

    def __init__(self, marketplace_dir: Path) -> None:
        self._root = marketplace_dir.resolve()

    # ------------------------------------------------------------------ #
    # Factory helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def init(
        cls,
        marketplace_dir: Path,
        *,
        name: str = "bulbasaur-team",
        owner_name: str = "team",
        description: str = "Bulbasaur team marketplace.",
    ) -> GitMarketplace:
        """Scaffold a new marketplace directory. Idempotent."""
        root = marketplace_dir.resolve()
        meta_dir = root / ".claude-plugin"
        plugins_dir = root / "plugins"

        meta_dir.mkdir(parents=True, exist_ok=True)
        plugins_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = meta_dir / "marketplace.json"
        if not manifest_path.exists():
            manifest = MarketplaceManifest(
                name=name,
                owner={"name": owner_name},
                description=description,
            )
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
            )

        # .gitkeep so the plugins/ directory is tracked in an empty repo.
        gitkeep = plugins_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

        return cls(root)

    # ------------------------------------------------------------------ #
    # Registry contract
    # ------------------------------------------------------------------ #

    def exists(self) -> bool:
        return (self._root / self._MARKETPLACE_JSON).exists()

    def load_manifest(self) -> MarketplaceManifest:
        path = self._root / self._MARKETPLACE_JSON
        if not path.exists():
            raise MarketplaceNotFoundError(
                f"marketplace.json not found at {path}. "
                "Run `bbsctl marketplace init <path>` first."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return MarketplaceManifest.from_dict(data)

    def save_manifest(self, manifest: MarketplaceManifest) -> None:
        path = self._root / self._MARKETPLACE_JSON
        manifest.generated_by = f"skillctl {__version__}"
        path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

    def list_plugins(self) -> list[MarketplaceEntry]:
        return self.load_manifest().plugins

    def get_plugin_dir(self, plugin_name: str) -> Path:
        return self._root / self._PLUGINS_DIR / plugin_name

    def plugin_exists(self, plugin_name: str) -> bool:
        return self.get_plugin_dir(plugin_name).exists()

    def publish_plugin(
        self,
        *,
        plugin_name: str,
        skill_name: str,
        skill_dir: Path,
        version: str = "0.1.0",
        description: str = "",
        strictness: str = "team",
        author_name: str = "anonymous",
        author_email: str | None = None,
        overwrite: bool = True,
    ) -> Path:
        """Copy a skill into the marketplace directory and update marketplace.json.

        Returns the path to the published plugin directory.
        """
        plugin_dir = self._root / self._PLUGINS_DIR / plugin_name
        skill_target_dir = plugin_dir / "skills" / skill_name
        plugin_meta_dir = plugin_dir / ".claude-plugin"

        if plugin_dir.exists() and overwrite:
            shutil.rmtree(plugin_dir)

        skill_target_dir.mkdir(parents=True, exist_ok=True)
        plugin_meta_dir.mkdir(parents=True, exist_ok=True)

        # Copy skill files.
        _copy_skill_files(src=skill_dir, dst=skill_target_dir)

        # Write plugin.json (Claude Code plugin spec).
        author: dict[str, str] = {"name": author_name}
        if author_email:
            author["email"] = author_email
        plugin_manifest = {
            "name": plugin_name,
            "version": version,
            "description": description,
            "author": author,
            "metadata": {"strictness": strictness},
        }
        (plugin_meta_dir / "plugin.json").write_text(
            json.dumps(plugin_manifest, indent=2), encoding="utf-8"
        )

        # Write bundle.lock + bundle.sig (signature is a placeholder until
        # Sigstore lands in Phase 3).
        from .bundle import write_bundle_lock, write_bundle_signature_placeholder

        write_bundle_lock(plugin_dir, name=plugin_name, version=version)
        write_bundle_signature_placeholder(plugin_dir)

        # Update marketplace.json.
        market_manifest = self.load_manifest()
        entry = MarketplaceEntry(
            name=plugin_name,
            source=f"./plugins/{plugin_name}",
            description=description,
            version=version,
            strictness=strictness,
        )
        # Upsert by name.
        market_manifest.plugins = [
            p for p in market_manifest.plugins if p.name != plugin_name
        ]
        market_manifest.plugins.append(entry)
        self.save_manifest(market_manifest)

        return plugin_dir

    def verify_plugin(self, plugin_name: str) -> tuple[bool, list[str]]:
        """Verify a published plugin's bundle.lock against on-disk contents.

        Returns (ok, errors). Called by `bbsctl install --verify` and by
        downstream marketplace consumers (CI, registry gateways).
        """
        from .bundle import verify_bundle

        plugin_dir = self.get_plugin_dir(plugin_name)
        if not plugin_dir.exists():
            return False, [f"plugin {plugin_name!r} not found in marketplace"]
        return verify_bundle(plugin_dir)

    def resolve_plugin(self, plugin_name: str) -> Path | None:
        """Return the plugin directory for `plugin_name`, or None if not found."""
        plugin_dir = self.get_plugin_dir(plugin_name)
        return plugin_dir if plugin_dir.exists() else None

    @property
    def root(self) -> Path:
        return self._root

    @property
    def name(self) -> str:
        try:
            return self.load_manifest().name
        except MarketplaceNotFoundError:
            return self._root.name


def _copy_skill_files(*, src: Path, dst: Path) -> None:
    skill_md = src / "SKILL.md"
    if skill_md.exists():
        shutil.copy2(skill_md, dst / "SKILL.md")
    # Recursive copies for content directories.
    for subdir in ("scripts", "references", "assets", "evals", "dist"):
        src_sub = src / subdir
        if src_sub.is_dir():
            dst_sub = dst / subdir
            if dst_sub.exists():
                shutil.rmtree(dst_sub)
            shutil.copytree(src_sub, dst_sub)
    # Single-file overlays carried with the bundle.
    for fname in ("skill.yaml", "permissions.yaml", "ownership.yaml"):
        src_file = src / fname
        if src_file.exists():
            shutil.copy2(src_file, dst / fname)


__all__ = [
    "GitMarketplace",
    "MarketplaceEntry",
    "MarketplaceManifest",
    "MarketplaceNotFoundError",
]
