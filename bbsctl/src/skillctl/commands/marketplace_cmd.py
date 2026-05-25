"""`bbsctl marketplace` — marketplace management subcommand group.

Phase 2 ships one subcommand:
  bbsctl marketplace init <path>   — scaffold a Git-backed marketplace directory

Phase 3+ will add: list, add-tenant, policy, federate.

The init subcommand produces a directory compatible with:
    /plugin marketplace add ./<path>    (stock Claude Code, zero patches)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from skillctl.marketplace.git_marketplace import GitMarketplace, MarketplaceNotFoundError
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


def _rel(path: Path) -> str:
    try:
        rel = path.relative_to(Path.cwd())
        display = f"./{rel}"
    except ValueError:
        display = str(path)
    return f"'{display}'" if " " in display else display


__all__ = ["register"]
