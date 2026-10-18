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
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from skillctl import __version__
from skillctl.durable import (
    atomic_write_json,
    file_lock,
    purge_stale_markers,
    replace_directory,
)



@dataclass
class MarketplaceEntry:
    """One plugin entry in the marketplace catalog."""

    name: str
    source: str          # relative path from marketplace root
    description: str
    version: str
    strictness: str = "local"
    display_name: str | None = None
    strict: bool | None = None
    default_enabled: bool | None = None
    skills: list[str] | None = None
    category: str | None = None
    keywords: list[str] | None = None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "source": self.source,
            "description": self.description,
            "version": self.version,
            "strictness": self.strictness,
        }
        if self.display_name is not None:
            d["displayName"] = self.display_name
        if self.strict is not None:
            d["strict"] = self.strict
        if self.default_enabled is not None:
            d["defaultEnabled"] = self.default_enabled
        if self.skills is not None:
            d["skills"] = self.skills
        if self.category is not None:
            d["category"] = self.category
        if self.keywords is not None:
            d["keywords"] = self.keywords
        return d


@dataclass
class MarketplaceManifest:
    name: str
    owner: dict[str, str]
    description: str
    plugins: list[MarketplaceEntry] = field(default_factory=list)
    generated_by: str = ""
    plugin_root: str = "./plugins"
    allow_cross_dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        metadata = {
            "generated_by": self.generated_by or f"skillctl {__version__}",
            "pluginRoot": self.plugin_root,
        }
        return {
            "name": self.name,
            "owner": self.owner,
            "description": self.description,
            "metadata": metadata,
            "allowCrossMarketplaceDependenciesOn": self.allow_cross_dependencies,
            "plugins": [
                e.to_dict() if hasattr(e, "to_dict") else {
                    "name": e.name,
                    "source": e.source,
                    "description": e.description,
                    "version": e.version,
                    "strictness": e.strictness,
                }
                for e in self.plugins
            ],
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
                display_name=p.get("displayName"),
                strict=p.get("strict"),
                default_enabled=p.get("defaultEnabled"),
                skills=p.get("skills"),
                category=p.get("category"),
                keywords=p.get("keywords"),
            )
            for p in data.get("plugins", [])
        ]
        metadata = data.get("metadata", {})
        plugin_root = metadata.get("pluginRoot", "./plugins")
        allow_cross = data.get("allowCrossMarketplaceDependenciesOn", [])
        return cls(
            name=data.get("name", ""),
            owner=data.get("owner", {"name": "unknown"}),
            description=data.get("description", ""),
            plugins=entries,
            generated_by=metadata.get("generated_by", ""),
            plugin_root=plugin_root,
            allow_cross_dependencies=allow_cross,
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
            atomic_write_json(manifest_path, manifest.to_dict())

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
        with file_lock(path):
            # Re-read under the lock so concurrent publishers do not clobber
            # each other's plugin entries when both called load_manifest earlier.
            if path.exists():
                on_disk = MarketplaceManifest.from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                by_name = {p.name: p for p in on_disk.plugins}
                for p in manifest.plugins:
                    by_name[p.name] = p
                merged = MarketplaceManifest(
                    name=manifest.name or on_disk.name,
                    owner=manifest.owner or on_disk.owner,
                    description=manifest.description or on_disk.description,
                    plugins=sorted(by_name.values(), key=lambda e: e.name),
                    generated_by=f"skillctl {__version__}",
                    plugin_root=manifest.plugin_root or on_disk.plugin_root,
                    allow_cross_dependencies=(
                        manifest.allow_cross_dependencies
                        or on_disk.allow_cross_dependencies
                    ),
                )
            else:
                merged = manifest
                merged.generated_by = f"skillctl {__version__}"
            atomic_write_json(path, merged.to_dict())

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
        # Resolve files & converters
        manifest_path = skill_dir / "manifest.yml"
        has_manifest = manifest_path.exists()

        derived_plugin_name = plugin_name
        derived_version = version
        derived_description = description
        derived_strictness = strictness

        if has_manifest:
            from skillctl.marketplace.converter import ManifestConverter, verify_strict_mode_conflict
            converter = ManifestConverter(skill_dir)
            # This will raise a clear ManifestConverterError / FrameworkError on validate failure
            converter.validate()
            plugin_json_data = converter.convert_to_plugin_json()
            derived_plugin_name = plugin_json_data["name"]
            derived_version = plugin_json_data["version"]
            derived_description = plugin_json_data["description"]
            derived_strictness = "team"  # catalog manifests default to team
            # Verify strict mode conflict on the source directory before publishing
            verify_strict_mode_conflict(skill_dir, converter.derive_strict_mode())

        plugins_root = self._root / self._PLUGINS_DIR
        purge_stale_markers(plugins_root)
        plugin_dir = plugins_root / derived_plugin_name

        if plugin_dir.exists() and not overwrite:
            raise FileExistsError(
                f"plugin {derived_plugin_name!r} already published at {plugin_dir}"
            )

        # Stage into a temp tree, then atomically replace the live plugin dir.
        # A crash mid-copy never leaves a half-written tree as the live path.
        staging_root = Path(
            tempfile.mkdtemp(prefix=f".{derived_plugin_name}.", dir=str(plugins_root))
        )
        try:
            skill_target_dir = staging_root / "skills" / skill_name
            plugin_meta_dir = staging_root / ".claude-plugin"
            skill_target_dir.mkdir(parents=True, exist_ok=True)
            plugin_meta_dir.mkdir(parents=True, exist_ok=True)

            _copy_skill_files(src=skill_dir, dst=skill_target_dir)

            if has_manifest:
                atomic_write_json(plugin_meta_dir / "plugin.json", plugin_json_data)
            else:
                author: dict[str, str] = {"name": author_name}
                if author_email:
                    author["email"] = author_email
                plugin_manifest = {
                    "name": derived_plugin_name,
                    "version": derived_version,
                    "description": derived_description,
                    "author": author,
                    "metadata": {"strictness": derived_strictness},
                }
                atomic_write_json(plugin_meta_dir / "plugin.json", plugin_manifest)

            from .bundle import write_bundle_lock, write_bundle_signature_placeholder

            write_bundle_lock(
                staging_root, name=derived_plugin_name, version=derived_version
            )
            write_bundle_signature_placeholder(staging_root)

            replace_directory(staging_root, plugin_dir)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

        market_manifest = self.load_manifest()

        if has_manifest:
            entry_data = converter.convert_to_marketplace_entry()
            entry = MarketplaceEntry(
                name=derived_plugin_name,
                source=f"./plugins/{derived_plugin_name}",
                description=derived_description,
                version=derived_version,
                strictness=derived_strictness,
                display_name=entry_data.get("displayName"),
                strict=entry_data.get("strict"),
                default_enabled=entry_data.get("defaultEnabled"),
                skills=entry_data.get("skills"),
                category=entry_data.get("category"),
                keywords=entry_data.get("keywords"),
            )
        else:
            entry = MarketplaceEntry(
                name=derived_plugin_name,
                source=f"./plugins/{derived_plugin_name}",
                description=derived_description,
                version=derived_version,
                strictness=derived_strictness,
            )

        market_manifest.plugins = [
            p for p in market_manifest.plugins if p.name != derived_plugin_name
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
