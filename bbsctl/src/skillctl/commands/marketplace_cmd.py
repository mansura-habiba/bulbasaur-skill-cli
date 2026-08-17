"""`bbsctl marketplace` — marketplace management subcommand group.

Subcommands:
  bbsctl marketplace init <path>         — scaffold a Git-backed marketplace directory
  bbsctl marketplace list [path]         — list plugins in a marketplace
  bbsctl marketplace export --catalog <catalog_root> --marketplace <path>
                                         — bulk-convert all OIC manifest.yml skills
                                           in a catalog directory to a marketplace

The init subcommand produces a directory compatible with:
    /plugin marketplace add ./<path>    (stock Claude Code, zero patches)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from skillctl.marketplace.git_marketplace import GitMarketplace, MarketplaceNotFoundError
from skillctl.marketplace.converter import ManifestConverter, ManifestConverterError
from skillctl.messaging import FrameworkError, emit, info


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "marketplace",
        help="Marketplace management (init, list, …)",
        description="Manage Bulbasaur marketplaces.",
    )
    sub = p.add_subparsers(dest="marketplace_command", metavar="<subcommand>")

    # ── marketplace init ─────────────────────────────────────────────────
    init_p = sub.add_parser(
        "init",
        help="Scaffold a new local marketplace directory",
        description=(
            "Create a Git-backed marketplace directory loadable by stock Claude Code "
            "via `/plugin marketplace add <path>`."
        ),
    )
    init_p.add_argument(
        "path",
        help="Directory to create the marketplace in (e.g. ./my-team-marketplace)",
    )
    init_p.add_argument(
        "--name",
        default=None,
        help="Marketplace identifier (default: directory name)",
    )
    init_p.add_argument(
        "--owner",
        default=None,
        metavar="NAME",
        help="Owner name recorded in marketplace.json (default: $USER or 'team')",
    )
    init_p.add_argument(
        "--description",
        default="Bulbasaur team marketplace.",
        help="Short description for the marketplace",
    )
    init_p.set_defaults(func=_run_init)

    # ── marketplace list ─────────────────────────────────────────────────
    list_p = sub.add_parser(
        "list",
        help="List plugins in a marketplace",
    )
    list_p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Marketplace directory (default: current directory)",
    )
    list_p.set_defaults(func=_run_list)

    # ── marketplace export ────────────────────────────────────────────────
    export_p = sub.add_parser(
        "export",
        help="Bulk-convert all OIC catalog skills (manifest.yml) to a marketplace",
        description=(
            "Walk a catalog root directory, find every skill with a manifest.yml, "
            "validate it, convert it to a Claude Code plugin descriptor, and register "
            "it in the target marketplace. Skips library-type, deprecated, and archived "
            "assets automatically and reports a per-skill summary at the end.\n\n"
            "Example:\n"
            "  bbsctl marketplace export \\\n"
            "    --catalog ./artifacts \\\n"
            "    --marketplace ./oic-marketplace"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_p.add_argument(
        "--catalog",
        required=True,
        metavar="PATH",
        help="Root directory of the OIC artifact catalog (e.g. ./artifacts)",
    )
    export_p.add_argument(
        "--marketplace",
        required=True,
        metavar="PATH",
        help="Path to the target Bulbasaur marketplace directory",
    )
    export_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate and report without writing any files",
    )
    export_p.set_defaults(func=_run_export)

    p.set_defaults(func=_no_subcommand(p))


def _no_subcommand(parser: argparse.ArgumentParser):
    def _run(args: argparse.Namespace) -> int:
        parser.print_help()
        return 0
    return _run


def _run_init(args: argparse.Namespace) -> int:
    target = Path(args.path).resolve()

    if target.exists() and (target / ".claude-plugin" / "marketplace.json").exists():
        info(f"marketplace already initialised at {target}")
        info("  Use `bbsctl marketplace list` to see its contents.")
        return 0

    name = args.name or target.name
    owner = args.owner or os.environ.get("USER") or os.environ.get("USERNAME") or "team"

    marketplace = GitMarketplace.init(
        target,
        name=name,
        owner_name=owner,
        description=args.description,
    )

    info(f"Marketplace initialised: {marketplace.root}")
    info(f"  name:  {name}")
    info(f"  owner: {owner}")
    info("")
    info("Next steps:")
    info("  # Publish a skill to this marketplace:")
    info(f"  bbsctl publish --marketplace {_rel(target)}")
    info("")
    info("  # In Claude Code, add this marketplace:")
    info(f"  /plugin marketplace add {_rel(target)}")
    return 0


def _run_list(args: argparse.Namespace) -> int:
    mp_dir = Path(args.path).resolve()
    marketplace = GitMarketplace(mp_dir)

    if not marketplace.exists():
        emit(
            FrameworkError(
                summary=f"not a Bulbasaur marketplace: {mp_dir}",
                fix=f"Run `bbsctl marketplace init {_rel(mp_dir)}` to create one first.",
            )
        )
        return 1

    try:
        plugins = marketplace.list_plugins()
    except MarketplaceNotFoundError as exc:
        emit(FrameworkError(summary=str(exc), fix="Re-run `bbsctl marketplace init`."))
        return 1

    if not plugins:
        info(f"marketplace `{marketplace.name}` has no plugins yet.")
        info("  Publish one with `bbsctl publish --marketplace <path>`.")
        return 0

    info(f"marketplace: {marketplace.name}  ({mp_dir})")
    info("")
    for p in plugins:
        info(f"  {p.name}@{p.version}  [{p.strictness}]  — {p.description or '(no description)'}")
    return 0


def _run_export(args: argparse.Namespace) -> int:
    catalog_root = Path(args.catalog).resolve()
    marketplace_path = Path(args.marketplace).resolve()
    dry_run: bool = args.dry_run

    if not catalog_root.is_dir():
        emit(
            FrameworkError(
                summary=f"catalog directory not found: {catalog_root}",
                fix="Pass a valid path with `--catalog <path>`.",
            )
        )
        return 1

    marketplace = GitMarketplace(marketplace_path)
    if not marketplace.exists():
        emit(
            FrameworkError(
                summary=f"marketplace not found: {marketplace_path}",
                fix=f"Run `bbsctl marketplace init {_rel(marketplace_path)}` first.",
            )
        )
        return 1

    # Discover all manifest.yml files under the catalog root.
    manifest_files = sorted(catalog_root.rglob("manifest.yml"))
    if not manifest_files:
        info(f"no manifest.yml files found under {catalog_root}")
        return 0

    skipped: list[tuple[str, str]] = []   # (path, reason)
    failed:  list[tuple[str, str]] = []   # (path, error)
    published: list[str] = []             # plugin names

    for manifest_path in manifest_files:
        skill_dir = manifest_path.parent
        rel = str(manifest_path.relative_to(catalog_root))

        converter = ManifestConverter(skill_dir)
        try:
            manifest = converter.load_manifest()
            asset_type = str(manifest.get("type") or "").strip().lower()
            status = str(manifest.get("status") or "").strip().lower()

            # Auto-skip non-publishable asset types and lifecycle states.
            if asset_type == "library":
                skipped.append((rel, "type:library (not a runnable artifact)"))
                continue
            if asset_type not in ("skill", "mcp-server"):
                skipped.append((rel, f"type:{asset_type} (unsupported — only skill/mcp-server)"))
                continue
            if status in ("deprecated", "archived"):
                skipped.append((rel, f"status:{status}"))
                continue

            converter.validate()

            if dry_run:
                plugin_json = converter.convert_to_plugin_json()
                info(f"  [dry-run] {rel}  →  {plugin_json['name']}")
                published.append(plugin_json["name"])
                continue

            plugin_dir = marketplace.publish_plugin(
                plugin_name=converter.convert_to_plugin_json()["name"],
                skill_name=manifest.get("name") or skill_dir.name,
                skill_dir=skill_dir,
            )
            published.append(plugin_dir.name)
            info(f"  published: {rel}  →  {plugin_dir.name}")

        except ManifestConverterError as exc:
            failed.append((rel, exc.framework_error.summary))
        except Exception as exc:  # noqa: BLE001
            failed.append((rel, str(exc)))

    # ── Summary ──────────────────────────────────────────────────────────
    info("")
    info(f"export {'(dry-run) ' if dry_run else ''}complete:")
    info(f"  published : {len(published)}")
    info(f"  skipped   : {len(skipped)}")
    info(f"  failed    : {len(failed)}")

    if skipped:
        info("")
        info("Skipped:")
        for path, reason in skipped:
            info(f"  {path}  — {reason}")

    if failed:
        info("")
        info("Failed:")
        for path, reason in failed:
            info(f"  {path}  — {reason}")

    if not dry_run and published:
        info("")
        info("Next steps:")
        info(f"  /plugin marketplace add {_rel(marketplace_path)}")

    return 1 if failed else 0


def _rel(path: Path) -> str:
    try:
        rel = path.relative_to(Path.cwd())
        display = f"./{rel}"
    except ValueError:
        display = str(path)
    return f"'{display}'" if " " in display else display


__all__ = ["register"]
