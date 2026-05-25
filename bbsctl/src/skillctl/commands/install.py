"""`bbsctl install` and `bbsctl add` — install skills from a marketplace.

Phase 2 supports Git/filesystem marketplaces (team strictness, no signing).
Signing verification at `org`+ lands in Phase 3.

    bbsctl install                        # install everything in skills.lock
    bbsctl add my-skill@./my-marketplace  # add a skill and update skills.lock
    bbsctl remove my-skill                # remove from skills.lock
    bbsctl list                           # list installed skills
    bbsctl lock                           # regenerate skills.lock without installing

The consumer cache: skills are copied to `.bulbasaur/cache/<plugin-name>/`
in the project directory. Claude Code reads from here via the seed directory
or the marketplace.json the consumer project maintains.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.marketplace.git_marketplace import GitMarketplace
from skillctl.marketplace.lock import LockPlugin, digest_plugin_dir, load_lock, write_lock
from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import load_project_config

_CACHE_DIR = ".bulbasaur/cache"


def register(subparsers: argparse._SubParsersAction) -> None:
    _register_install(subparsers)
    _register_add(subparsers)
    _register_remove(subparsers)
    _register_list_cmd(subparsers)
    _register_lock(subparsers)


# ── install ─────────────────────────────────────────────────────────────────

def _register_install(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "install",
        help="Install all skills from skills.lock",
        description=(
            "Install every skill recorded in skills.lock into the local cache. "
            "Deterministic: same lock → same result."
        ),
    )
    p.add_argument(
        "--dir",
        default=None,
        help="Project directory (default: current directory)",
    )
    p.set_defaults(func=_run_install)


def _run_install(args: argparse.Namespace) -> int:
    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    lock = load_lock(project_dir)

    if not lock.plugins:
        info("skills.lock is empty. Run `bbsctl add <skill>@<marketplace>` first.")
        return 0

    config = load_project_config(project_dir)
    cache_dir = project_dir / _CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    errors = 0
    for plugin in lock.plugins:
        mp_ref = _find_marketplace_for_plugin(plugin, lock, config)
        if mp_ref is None:
            emit(
                FrameworkError(
                    summary=f"cannot resolve marketplace for `{plugin.name}`",
                    detail=f"source recorded in lock: {plugin.source!r}",
                    fix=(
                        "Ensure the marketplace path in skills.lock is accessible, "
                        "or re-add the skill with `bbsctl add`."
                    ),
                )
            )
            errors += 1
            continue

        result = _install_plugin(plugin, mp_ref=mp_ref, cache_dir=cache_dir)
        if result:
            info(f"  installed {plugin.name}@{plugin.version}")
        else:
            errors += 1

    if errors:
        info(f"{errors} error(s) during install.")
        return 1
    info(f"Installed {len(lock.plugins)} skill(s) into {cache_dir}")
    return 0


# ── add ──────────────────────────────────────────────────────────────────────

def _register_add(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "add",
        help="Add a skill dependency and update skills.lock",
        description=(
            "Resolve `<skill>@<marketplace>` from a marketplace, copy it to the "
            "local cache, and write the entry to skills.lock. Use `--staged` to "
            "install a skill previously downloaded with `bbsctl fetch`."
        ),
    )
    p.add_argument(
        "spec",
        help="Skill spec in the form `<skill-name>@<marketplace-path>` or just `<skill-name>` "
             "(uses default marketplace from project config)",
    )
    p.add_argument(
        "--staged",
        action="store_true",
        default=False,
        help="Install from the staging area (populated by `bbsctl fetch`)",
    )
    p.add_argument(
        "--dir",
        default=None,
        help="Project directory (default: current directory)",
    )
    p.set_defaults(func=_run_add)


def _run_add(args: argparse.Namespace) -> int:
    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd()

    if getattr(args, "staged", False):
        return _run_add_staged(args.spec.strip(), project_dir)

    config = load_project_config(project_dir)

    skill_name, mp_ref = _parse_spec(args.spec, default_marketplace=config.marketplace)
    if mp_ref is None:
        emit(
            FrameworkError(
                summary=f"no marketplace specified for `{skill_name}`",
                fix=(
                    "Use `<skill>@<marketplace-path>` (e.g. `my-skill@./my-team-marketplace`), "
                    "or set a default marketplace in [tool.bulbasaur] via "
                    "`bbsctl init --marketplace <path>`."
                ),
            )
        )
        return 1

    mp_path = Path(mp_ref).resolve()
    marketplace = GitMarketplace(mp_path)
    if not marketplace.exists():
        emit(
            FrameworkError(
                summary=f"marketplace not found: {mp_path}",
                fix=f"Run `bbsctl marketplace init {mp_ref}` to create it first.",
            )
        )
        return 1

    plugin_dir = marketplace.resolve_plugin(skill_name)
    if plugin_dir is None:
        available = [p.name for p in marketplace.list_plugins()]
        emit(
            FrameworkError(
                summary=f"skill `{skill_name}` not found in marketplace `{marketplace.name}`",
                detail=f"marketplace: {mp_path}",
                fix=(
                    f"Available skills: {available or ['(none yet)']}. "
                    f"Publish first with `bbsctl publish --marketplace {mp_ref}`."
                ),
            )
        )
        return 1

    # Resolve version from marketplace.json.
    entries = {e.name: e for e in marketplace.list_plugins()}
    entry = entries.get(skill_name)
    version = entry.version if entry else "0.1.0"
    strictness = entry.strictness if entry else "local"

    # Copy into local cache.
    cache_dir = project_dir / _CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / skill_name
    import shutil
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(plugin_dir, dst)

    digest = digest_plugin_dir(plugin_dir)

    # Update skills.lock.
    lock = load_lock(project_dir)
    lock.add_marketplace(mp_ref)
    lock.add_or_update_plugin(
        LockPlugin(
            name=skill_name,
            version=version,
            strictness=strictness,
            digest=digest,
            source=f"{mp_ref}#{skill_name}@{version}",
        )
    )
    lock_path = write_lock(lock, project_dir)

    info(f"Added {skill_name}@{version} [{strictness}]")
    info(f"  cache: {dst}")
    info(f"  lock:  {lock_path}")
    return 0


_STAGING_DIR = ".bulbasaur/staging"


def _run_add_staged(skill_name: str, project_dir: Path) -> int:
    """Install a skill from the staging area (populated by `bbsctl fetch`)."""
    staging_dir = project_dir / _STAGING_DIR / skill_name
    if not staging_dir.exists() or not (staging_dir / "SKILL.md").exists():
        emit(
            FrameworkError(
                summary=f"skill `{skill_name}` not found in staging area",
                detail=f"expected at: {staging_dir}",
                fix=(
                    f"Run `bbsctl fetch <source> --skill {skill_name}` first "
                    "to download and stage the skill."
                ),
            )
        )
        return 1

    cache_dir = project_dir / _CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / skill_name
    if dst.exists():
        import shutil as _shutil
        _shutil.rmtree(dst)
    import shutil as _shutil
    _shutil.copytree(staging_dir, dst)

    digest = digest_plugin_dir(staging_dir)

    lock = load_lock(project_dir)
    lock.add_or_update_plugin(
        LockPlugin(
            name=skill_name,
            version="0.1.0",
            strictness="local",
            digest=digest,
            source=f"staged#{skill_name}@0.1.0",
        )
    )
    lock_path = write_lock(lock, project_dir)

    info(f"Added {skill_name} from staging area")
    info(f"  cache: {dst}")
    info(f"  lock:  {lock_path}")

    # Clean up staging.
    import shutil as _shutil
    _shutil.rmtree(staging_dir)
    info(f"  staging cleaned: {staging_dir}")
    return 0


# ── remove ───────────────────────────────────────────────────────────────────

def _register_remove(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "remove",
        help="Remove a skill from skills.lock",
    )
    p.add_argument("name", help="Skill name to remove")
    p.add_argument("--dir", default=None)
    p.set_defaults(func=_run_remove)


def _run_remove(args: argparse.Namespace) -> int:
    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    lock = load_lock(project_dir)

    if not lock.remove_plugin(args.name):
        emit(
            FrameworkError(
                summary=f"`{args.name}` not found in skills.lock",
                fix="Check the name with `bbsctl list`.",
            )
        )
        return 1

    write_lock(lock, project_dir)

    # Remove from cache.
    cache_dir = project_dir / _CACHE_DIR / args.name
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)

    info(f"Removed {args.name} from skills.lock and cache.")
    return 0


# ── list ─────────────────────────────────────────────────────────────────────

def _register_list_cmd(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "list",
        help="List installed skills (from skills.lock)",
    )
    p.add_argument("--dir", default=None)
    p.set_defaults(func=_run_list)


def _run_list(args: argparse.Namespace) -> int:
    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    lock = load_lock(project_dir)

    if not lock.plugins:
        info("No skills installed. Run `bbsctl add <skill>@<marketplace>`.")
        return 0

    info(f"Installed skills ({len(lock.plugins)}):")
    for p in sorted(lock.plugins, key=lambda x: x.name):
        info(f"  {p.name}@{p.version}  [{p.strictness}]")
        info(f"    source: {p.source}")
    return 0


# ── lock ──────────────────────────────────────────────────────────────────────

def _register_lock(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "lock",
        help="Regenerate skills.lock without installing",
    )
    p.add_argument("--dir", default=None)
    p.set_defaults(func=_run_lock)


def _run_lock(args: argparse.Namespace) -> int:
    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    lock = load_lock(project_dir)
    path = write_lock(lock, project_dir)
    info(f"skills.lock written: {path}  ({len(lock.plugins)} plugin(s))")
    return 0


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_spec(spec: str, *, default_marketplace: str | None) -> tuple[str, str | None]:
    """Split `skill@marketplace` into (skill_name, marketplace_ref)."""
    if "@" in spec:
        skill, mp = spec.split("@", 1)
        return skill.strip(), mp.strip() or default_marketplace
    return spec.strip(), default_marketplace


def _find_marketplace_for_plugin(plugin, lock, config) -> str | None:
    """Infer the marketplace ref from the plugin's `source` field or lock marketplaces."""
    if "#" in plugin.source:
        return plugin.source.split("#")[0]
    if lock.marketplaces:
        return lock.marketplaces[0].ref
    return config.marketplace


def _install_plugin(plugin, *, mp_ref: str, cache_dir: Path) -> bool:
    """Resolve and copy a plugin from its marketplace into the cache."""
    mp_path = Path(mp_ref).resolve()
    marketplace = GitMarketplace(mp_path)
    plugin_dir = marketplace.resolve_plugin(plugin.name)
    if plugin_dir is None:
        emit(
            FrameworkError(
                summary=f"skill `{plugin.name}` not found in marketplace at {mp_path}",
                fix="Re-add the skill with `bbsctl add`.",
            )
        )
        return False
    import shutil
    dst = cache_dir / plugin.name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(plugin_dir, dst)
    return True


__all__ = ["register"]
