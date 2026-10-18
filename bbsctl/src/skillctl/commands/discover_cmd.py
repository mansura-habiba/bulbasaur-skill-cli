"""`bbsctl discover` — emit ARD manifests for skill discovery.

Discovery only. Does not install or publish packages.
Pair with `bbsctl publish` for Claude / catalog marketplace packaging.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillctl.marketplace.ard import (
    ArdEmitError,
    artifact_to_ard_entry,
    catalog_to_ard_entries,
    skill_to_ard_entry,
    write_ard_manifest,
)
from skillctl.messaging import emit, info


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "discover",
        help="Emit ard.json for Agentic Resource Discovery",
        description=(
            "Emit an ARD manifest so discovery services can find skills "
            "before invoke (https://agenticresourcediscovery.org/).\n\n"
            "This does not install or package skills. Use `bbsctl publish` "
            "for Claude / catalog marketplace packaging.\n\n"
            "Examples:\n"
            "  bbsctl discover ./my-skill --domain example.com\n"
            "  bbsctl discover ./artifacts --catalog --domain github.ibm.com\n"
            "  # Host at https://<domain>/.well-known/ard.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Skill directory, catalog artifact folder, or catalog root (with --catalog)",
    )
    p.add_argument(
        "--catalog",
        action="store_true",
        default=False,
        help="Treat path as an artifacts/ tree; one entry per active skill",
    )
    p.add_argument(
        "--domain",
        default="local",
        help="Domain for urn:air:<domain>:skill:<name> (default: local)",
    )
    p.add_argument(
        "--url",
        default=None,
        help="Canonical URL for the skill resource (default: file:// or source_repo)",
    )
    p.add_argument(
        "--base-url",
        default=None,
        help="With --catalog, prefix for per-artifact SKILL.md URLs",
    )
    p.add_argument(
        "--query",
        action="append",
        default=[],
        metavar="TEXT",
        help="Representative query for semantic discovery (repeatable)",
    )
    p.add_argument(
        "--output",
        "-o",
        default="ard.json",
        help="Output path (default: ./ard.json)",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        default=False,
        help="Print JSON to stdout instead of writing a file",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    try:
        if args.catalog:
            entries = catalog_to_ard_entries(
                path, domain=args.domain, base_url=args.base_url
            )
            if not entries:
                info(f"no active skills found under {path}")
                return 0
        elif (path / "manifest.yml").is_file():
            entries = [
                artifact_to_ard_entry(
                    path,
                    domain=args.domain,
                    url=args.url,
                    queries=args.query or None,
                )
            ]
        elif path.name == "src" and (path.parent / "manifest.yml").is_file():
            entries = [
                artifact_to_ard_entry(
                    path.parent,
                    domain=args.domain,
                    url=args.url,
                    queries=args.query or None,
                )
            ]
        else:
            entries = [
                skill_to_ard_entry(
                    path,
                    domain=args.domain,
                    url=args.url,
                    queries=args.query or None,
                )
            ]
    except ArdEmitError as exc:
        emit(exc.framework_error)
        return 1

    if args.stdout:
        sys.stdout.write(json.dumps({"entries": entries}, indent=2) + "\n")
        return 0

    out = write_ard_manifest(entries, Path(args.output), upsert=True)
    info(f"wrote {len(entries)} ARD entr{'y' if len(entries) == 1 else 'ies'} → {out}")
    info("Host at https://<domain>/.well-known/ard.json for public discovery crawlers.")
    return 0


__all__ = ["register", "run"]
