"""`bbsctl publish` — package a skill for consumers.

One verb covers every packaging target:

  bbsctl publish                         # local Claude marketplace (default)
  bbsctl publish --marketplace ./mp      # team Git marketplace (plugins/ copy)
  bbsctl publish artifacts/.../slug --inplace   # catalog curation in-place
  bbsctl publish … --ard                 # also emit ard.json (or use bbsctl discover)

Discovery without packaging is `bbsctl discover`.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from skillctl.agentskills import parse_skill_md
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.marketplace.ard import (
    ArdEmitError,
    artifact_to_ard_entry,
    skill_to_ard_entry,
    write_ard_manifest,
)
from skillctl.marketplace.catalog_publish import (
    CatalogPublishError,
    find_repo_root,
    publish_catalog_artifact,
)
from skillctl.marketplace.converter import ManifestConverter, ManifestConverterError
from skillctl.marketplace.git_marketplace import GitMarketplace
from skillctl.messaging import FrameworkError, emit, info
from skillctl.publish import build_target, list_targets
from skillctl.publish.factory import target_description
from skillctl.publish.target import PublishContext
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    """Wire the `publish` subcommand into the CLI."""
    target_help = " | ".join(
        f"{name}: {target_description(name)}" for name in list_targets()
    )
    p = subparsers.add_parser(
        "publish",
        help="Publish a skill (local Claude, team marketplace, or catalog in-place)",
        description=(
            "Package a skill for consumers. One command, three layouts:\n"
            "  default              → claude-code-local marketplace next to the skill\n"
            "  --marketplace PATH   → copy into a team Git marketplace plugins/\n"
            "  --inplace / artifacts path → in-place .claude-plugin entry\n\n"
            "For discovery-only (ARD), use `bbsctl discover`."
        ),
        epilog=f"Available --target values:\n  {target_help}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Skill directory or catalog artifact folder (default: current directory)",
    )
    p.add_argument(
        "--target",
        default="claude-code-local",
        choices=list_targets(),
        help=(
            "Publish target when not using --marketplace / --inplace "
            "(default: claude-code-local)"
        ),
    )
    p.add_argument(
        "--output",
        default=None,
        help=(
            "Output directory for the target's artifacts. "
            "For claude-code-local, default is `./bulbasaur-marketplace` next to CWD."
        ),
    )
    p.add_argument(
        "--marketplace",
        default=None,
        metavar="PATH",
        help="Team marketplace directory (copies skill into plugins/)",
    )
    p.add_argument(
        "--inplace",
        action="store_true",
        default=False,
        help=(
            "In-place catalog publish into .claude-plugin/marketplace.json "
            "(no file copy; source points at artifacts/.../src)"
        ),
    )
    p.add_argument(
        "--repo-root",
        default=None,
        metavar="PATH",
        help="Catalog curation repo root (default: auto-detect artifacts/ + .claude-plugin/)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate and print without writing (inplace / team marketplace paths)",
    )
    p.add_argument(
        "--ard",
        action="store_true",
        default=False,
        help="Also emit/update ard.json (same as a follow-up `bbsctl discover`)",
    )
    p.add_argument(
        "--ard-domain",
        default="local",
        help="Domain for urn:air:<domain>:skill:<name> when --ard is set",
    )
    p.add_argument(
        "--ard-out",
        default=None,
        metavar="PATH",
        help="ard.json output path (default: repo-root/ard.json or ./ard.json)",
    )
    p.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Target-specific option (repeatable). E.g. `--option marketplace_name=acme`.",
    )
    p.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help="Override strictness for this publish (default: read from skill.yaml or LOCAL)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Execute `bbsctl publish`."""
    path = Path(args.skill_dir).resolve()

    # ── Catalog in-place (artifacts/ + .claude-plugin/) ───────────────────
    if args.inplace or _looks_like_catalog_artifact(
        path, force_marketplace=bool(args.marketplace)
    ):
        return _run_inplace_publish(args, path)

    skill_dir = path
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        # Allow catalog src/ layout without --inplace when SKILL.md is nested
        nested = skill_dir / "src" / "SKILL.md"
        if nested.is_file() and (skill_dir / "manifest.yml").is_file():
            return _run_inplace_publish(args, skill_dir)
        emit(
            FrameworkError(
                summary=f"SKILL.md not found at {skill_md}",
                fix=(
                    "Run `bbsctl new <name>`, `cd` into a skill, or pass a catalog "
                    "artifacts/<squad>/<team>/<slug> path with `--inplace`."
                ),
            )
        )
        return 1

    try:
        frontmatter = parse_skill_md(skill_md)
    except AgentSkillsValidationError as exc:
        emit(
            FrameworkError(
                summary=f"{exc.field}: {exc.message}",
                detail=f"agentskills.io rule violation (code={exc.code})",
                fix=exc.fix,
                docs="https://agentskills.io/specification",
            )
        )
        return 1

    if getattr(args, "marketplace", None):
        code = _run_team_marketplace_publish(
            skill_dir=skill_dir,
            frontmatter=frontmatter,
            marketplace_path=Path(args.marketplace).resolve(),
            strictness=Strictness.from_string(args.strictness),
            dry_run=bool(args.dry_run),
        )
        if code == 0 and args.ard and not args.dry_run:
            _emit_ard(skill_dir, args)
        return code

    options = _parse_options(args.option)
    if options is None:
        return 1

    try:
        target = build_target(args.target)
    except ValueError as exc:
        emit(
            FrameworkError(
                summary="unknown publish target",
                detail=str(exc),
                fix=f"Pick one of: {', '.join(list_targets())}",
            )
        )
        return 1

    output_dir = _resolve_output_dir(
        args.output, target_name=args.target, skill_dir=skill_dir
    )
    strictness = Strictness.from_string(args.strictness)

    if not strictness.includes(target.min_strictness):
        emit(
            FrameworkError(
                summary=(
                    f"target `{args.target}` requires strictness "
                    f"≥ {target.min_strictness.value}"
                ),
                detail=f"this skill is at strictness {strictness.value}",
                fix=(
                    f"Run `bbsctl strictness {target.min_strictness.value}` first, "
                    "or pick a lower-floor target (e.g. `--target claude-code-local`)."
                ),
            )
        )
        return 1

    context = PublishContext(
        skill_dir=skill_dir,
        frontmatter=frontmatter,
        strictness=strictness,
        output_dir=output_dir,
        target_options=options,
    )
    result = target.publish(context)
    _print_result(result)
    if result.success and args.ard:
        _emit_ard(skill_dir, args)
    return 0 if result.success else 1


def _looks_like_catalog_artifact(path: Path, *, force_marketplace: bool) -> bool:
    if force_marketplace:
        return False
    if not (path / "manifest.yml").is_file():
        return False
    return find_repo_root(path) is not None


def _run_inplace_publish(args: argparse.Namespace, path: Path) -> int:
    try:
        result = publish_catalog_artifact(
            path,
            repo_root=Path(args.repo_root).resolve() if args.repo_root else None,
            dry_run=bool(args.dry_run),
        )
    except CatalogPublishError as exc:
        emit(exc.framework_error)
        return 1

    tag = "[dry-run] " if result["dry_run"] else ""
    mp_name = result.get("marketplace_name") or "catalog"
    info(f"{tag}published `{result['name']}` → source {result['source']}")
    info(f"  claude marketplace: {result['claude_path']}")
    info(f"  sidecar:            {result['sidecar_path']}")
    if not args.dry_run:
        info("")
        info("Consumers install with:")
        info("  /plugin marketplace add <path-or-git-url-of-this-curation-repo>")
        info(f"  /plugin install {result['name']}@{mp_name}")
        if args.ard:
            ard_out = (
                Path(args.ard_out)
                if args.ard_out
                else Path(result["claude_path"]).resolve().parents[1] / "ard.json"
            )
            _emit_ard(path, args, output=ard_out)
    return 0


def _run_team_marketplace_publish(
    *,
    skill_dir: Path,
    frontmatter,
    marketplace_path: Path,
    strictness: Strictness,
    dry_run: bool = False,
) -> int:
    marketplace = GitMarketplace(marketplace_path)
    if not marketplace.exists():
        emit(
            FrameworkError(
                summary=f"marketplace not found: {marketplace_path}",
                fix=f"Run `bbsctl marketplace init {marketplace_path}` first.",
            )
        )
        return 1

    manifest_path = skill_dir / "manifest.yml"
    if manifest_path.exists():
        converter = ManifestConverter(skill_dir)
        try:
            converter.validate()
            plugin_json = converter.convert_to_plugin_json()
            skill_name = converter.load_manifest().get("name") or skill_dir.name
            plugin_name = plugin_json["name"]
            description = plugin_json.get("description", "")
        except ManifestConverterError as exc:
            emit(exc.framework_error)
            return 1
    else:
        skill_name = frontmatter.name or skill_dir.name
        plugin_name = f"{skill_name}-plugin"
        description = frontmatter.description or ""

    if dry_run:
        info(f"[dry-run] would publish {skill_name} → {plugin_name} in {marketplace_path}")
        return 0

    author_name = os.environ.get("USER") or "anonymous"
    try:
        plugin_dir = marketplace.publish_plugin(
            plugin_name=plugin_name,
            skill_name=skill_name,
            skill_dir=skill_dir,
            description=description,
            strictness=strictness.value,
            author_name=author_name,
        )
    except Exception as exc:
        emit(
            FrameworkError(
                summary=f"publish failed: {exc}",
                fix="Check marketplace path and permissions.",
            )
        )
        return 1

    mp_name = marketplace.name
    info(f"published to marketplace `{mp_name}`")
    info(f"  plugin: {plugin_dir}")
    info("")
    info("Next steps:")
    info(f"  /plugin marketplace add {marketplace_path}")
    info(f"  /plugin install {plugin_name}@{mp_name}")
    return 0


def _emit_ard(
    path: Path, args: argparse.Namespace, *, output: Path | None = None
) -> None:
    out = output or (Path(args.ard_out) if args.ard_out else Path("ard.json"))
    domain = getattr(args, "ard_domain", "github.ibm.com")
    try:
        if (path / "manifest.yml").is_file():
            entries = [artifact_to_ard_entry(path, domain=domain)]
        else:
            entries = [skill_to_ard_entry(path, domain=domain)]
        written = write_ard_manifest(entries, out, upsert=True)
        info(f"  ard.json: {written}")
    except ArdEmitError as exc:
        emit(exc.framework_error)


def _parse_options(raw: list[str]) -> dict[str, str] | None:
    out: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            emit(
                FrameworkError(
                    summary=f"malformed --option value: {item!r}",
                    fix=(
                        "Use the form `--option key=value` "
                        "(e.g. `--option marketplace_name=acme`)."
                    ),
                )
            )
            return None
        key, value = item.split("=", 1)
        out[key.strip()] = value
    return out


def _resolve_output_dir(
    override: str | None, *, target_name: str, skill_dir: Path
) -> Path:
    if override:
        return Path(override).resolve()
    if target_name == "claude-code-local":
        return (skill_dir.parent / "bulbasaur-marketplace").resolve()
    return (skill_dir / "dist" / target_name).resolve()


def _print_result(result) -> None:
    if result.success:
        info(f"published via {result.target_name}")
        for label, path in result.artifacts.items():
            info(f"  · {label}: {path}")
        if result.next_steps:
            info("")
            info("Next steps:")
            for line in result.next_steps:
                info(f"  {line}" if line else "")
    else:
        info(f"publish failed (target={result.target_name})")
        for line in result.next_steps:
            info(f"  {line}")


__all__ = ["register", "run"]
