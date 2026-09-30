"""`bbsctl plugin` — plugin subcommand group for manifest/descriptor management."""

from __future__ import annotations

import argparse
import os
import json
from pathlib import Path

from skillctl.marketplace.converter import ManifestConverter, verify_strict_mode_conflict, ManifestConverterError
from skillctl.marketplace.git_marketplace import GitMarketplace
from skillctl.messaging import FrameworkError, emit, info
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "plugin",
        help="Plugin and descriptor management (generate, publish, …)",
        description="Manage Claude Code plugin descriptors and manifest.yml files.",
    )
    sub = p.add_subparsers(dest="plugin_command", metavar="<subcommand>")

    # ── plugin generate ──────────────────────────────────────────────────
    gen_p = sub.add_parser(
        "generate",
        help="Generate a compliant plugin.json descriptor from manifest.yml",
        description=(
            "Parse the local manifest.yml, run the 6-checkpoint validation, "
            "and generate a compliant .claude-plugin/plugin.json file."
        ),
    )
    gen_p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory containing manifest.yml (default: current directory)",
    )
    gen_p.set_defaults(func=_run_generate)

    # ── plugin publish ───────────────────────────────────────────────────
    pub_p = sub.add_parser(
        "publish",
        help="Publish the plugin directly to a marketplace folder",
        description=(
            "Enforce validation checkpoints, convert manifest.yml, "
            "and publish the skill package to a Git-backed marketplace in one transaction."
        ),
    )
    pub_p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory containing manifest.yml (default: current directory)",
    )
    pub_p.add_argument(
        "--marketplace",
        required=True,
        metavar="PATH",
        help="Path to the Bulbasaur team marketplace directory",
    )
    pub_p.set_defaults(func=_run_publish)

    p.set_defaults(func=_no_subcommand(p))


def _no_subcommand(parser: argparse.ArgumentParser):
    def _run(args: argparse.Namespace) -> int:
        parser.print_help()
        return 0
    return _run


def _run_generate(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()

    converter = ManifestConverter(skill_dir)
    try:
        manifest = converter.load_manifest()
        info(f"parsed manifest.yml for '{manifest.get('name', skill_dir.name)}'")

        # 6-checkpoint validation
        warnings = converter.validate()

        name = manifest.get("name") or skill_dir.name
        info(f"reserved name check: PASS ('{name}-plugin' is not reserved)")

        strict = converter.derive_strict_mode()
        info(f"strict mode: derived {str(strict).lower()} ({'first-party' if strict else 'external hosted'}, level={manifest.get('level', 'team')})")

        # Create .claude-plugin directory if not exists
        plugin_meta_dir = skill_dir / ".claude-plugin"
        plugin_meta_dir.mkdir(parents=True, exist_ok=True)

        plugin_json_data = converter.convert_to_plugin_json()
        plugin_json_path = plugin_meta_dir / "plugin.json"

        # Verify strict mode conflicts before writing
        verify_strict_mode_conflict(skill_dir, strict)

        plugin_json_path.write_text(
            json.dumps(plugin_json_data, indent=2), encoding="utf-8"
        )

        for warning in warnings:
            info(f"  WARN: {warning}")

        info(f"validated {6 - len(warnings)} checkpoints successfully")
        info(f"generated '{plugin_json_path}'")
        info(f"  displayName: \"{manifest.get('title') or name}\"")
        info("  defaultEnabled: true")
        return 0

    except ManifestConverterError as exc:
        emit(exc.framework_error)
        return 1
    except Exception as exc:
        emit(FrameworkError(
            summary=f"generate failed: {exc}",
            fix="Check your manifest.yml format and permissions.",
        ))
        return 1


def _run_publish(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    marketplace_path = Path(args.marketplace).resolve()

    marketplace = GitMarketplace(marketplace_path)
    if not marketplace.exists():
        emit(
            FrameworkError(
                summary=f"marketplace not found: {marketplace_path}",
                fix=f"Run `bbsctl marketplace init {marketplace_path}` first.",
            )
        )
        return 1

    converter = ManifestConverter(skill_dir)
    try:
        # Load and validate first
        manifest = converter.load_manifest()
        converter.validate()

        skill_name = manifest.get("name") or skill_dir.name
        plugin_name = f"{skill_name}-plugin"
        author_name = os.environ.get("USER") or "anonymous"

        plugin_dir = marketplace.publish_plugin(
            plugin_name=plugin_name,
            skill_name=skill_name,
            skill_dir=skill_dir,
            description=manifest.get("title") or manifest.get("description") or "",
            strictness="team",
            author_name=author_name,
        )

        mp_name = marketplace.name
        info(f"published to marketplace `{mp_name}`")
        info(f"  plugin: {plugin_dir}")
        info("")
        info("Next steps:")
        info(f"  /plugin marketplace add {marketplace_path}")
        info(f"  /plugin install {plugin_name}@{mp_name}")
        return 0

    except ManifestConverterError as exc:
        emit(exc.framework_error)
        return 1
    except Exception as exc:
        emit(FrameworkError(
            summary=f"publish failed: {exc}",
            fix="Check marketplace path, manifest.yml, and write permissions.",
        ))
        return 1


__all__ = ["register"]
