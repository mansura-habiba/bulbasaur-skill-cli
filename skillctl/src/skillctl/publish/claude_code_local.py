"""Claude Code local-marketplace publish target.

Builds a directory layout that stock Claude Code can load via:

    /plugin marketplace add ./<marketplace-dir>
    /plugin install <plugin-name>@<marketplace-name>

Layout produced (matches the public Claude Code plugin spec):

    <marketplace-dir>/
    ├── .claude-plugin/
    │   └── marketplace.json
    └── plugins/
        └── <skill-name>-plugin/
            ├── .claude-plugin/
            │   └── plugin.json
            └── skills/
                └── <skill-name>/
                    └── SKILL.md

No signing, no enterprise overlay — this is the `local` strictness path.
The framework is committed to stock-Claude-Code interop with zero patches
(framework-build-plan.md §0.3 "the framework composes with developer tools"),
so this target produces exactly what `/plugin marketplace add` expects.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from skillctl import __version__

from .target import PublishContext, PublishResult, PublishTarget


# Public Claude Code plugin spec reserves certain marketplace names. Ours must
# not collide. See https://code.claude.com/docs/en/plugin-marketplaces.
_DEFAULT_MARKETPLACE_NAME = "bulbasaur-local"


class ClaudeCodeLocalTarget(PublishTarget):
    """Local Claude Code marketplace target.

    Options (via `--option k=v`):
      marketplace_name  override the marketplace identifier (default: bulbasaur-local)
      author_name       override the author name (default: $USER or "anonymous")
      author_email      override the author email (default: unset)
    """

    name = "claude-code-local"
    description = (
        "Build a local marketplace directory loadable by stock Claude Code "
        "via /plugin marketplace add ./<dir>. No signing; no API key needed."
    )

    def publish(self, context: PublishContext) -> PublishResult:
        opts = context.target_options
        marketplace_name = opts.get("marketplace_name", _DEFAULT_MARKETPLACE_NAME)
        author_name = opts.get("author_name") or _detect_author_name()
        author_email = opts.get("author_email")

        marketplace_dir = context.output_dir
        skill_name = context.frontmatter.name or "unnamed-skill"
        plugin_name = f"{skill_name}-plugin"

        # Build the directory shape. We tolerate existing dirs (allows re-publish).
        plugin_dir = marketplace_dir / "plugins" / plugin_name
        skill_target_dir = plugin_dir / "skills" / skill_name
        marketplace_meta_dir = marketplace_dir / ".claude-plugin"
        plugin_meta_dir = plugin_dir / ".claude-plugin"

        for d in (marketplace_meta_dir, plugin_meta_dir, skill_target_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Copy SKILL.md (and any scripts/, references/, assets/) from the source skill.
        _copy_skill_files(src=context.skill_dir, dst=skill_target_dir)

        # marketplace.json — the public Claude Code marketplace catalog format.
        marketplace_manifest = {
            "name": marketplace_name,
            "owner": _author_object(author_name, author_email),
            "description": "Bulbasaur-published skills (local marketplace).",
            "plugins": [
                {
                    "name": plugin_name,
                    "source": f"./plugins/{plugin_name}",
                    "description": context.frontmatter.description or "",
                    "version": "0.1.0",
                }
            ],
            "metadata": {
                "generated_by": f"skillctl {__version__}",
                "strictness": context.strictness.value,
            },
        }
        marketplace_json_path = marketplace_meta_dir / "marketplace.json"
        marketplace_json_path.write_text(
            json.dumps(marketplace_manifest, indent=2), encoding="utf-8"
        )

        # plugin.json — the public Claude Code plugin manifest.
        plugin_manifest = {
            "name": plugin_name,
            "version": "0.1.0",
            "description": context.frontmatter.description or "",
            "author": _author_object(author_name, author_email),
        }
        plugin_json_path = plugin_meta_dir / "plugin.json"
        plugin_json_path.write_text(json.dumps(plugin_manifest, indent=2), encoding="utf-8")

        # Build the next-steps the CLI will print.
        rel_marketplace = _relativize_for_display(marketplace_dir)
        next_steps = [
            f"# 1. In Claude Code, add this marketplace:",
            f"/plugin marketplace add {rel_marketplace}",
            "",
            f"# 2. Install the plugin from the marketplace:",
            f"/plugin install {plugin_name}@{marketplace_name}",
            "",
            f"# 3. Invoke the skill (Claude Code namespaces plugin skills as plugin:skill):",
            f"/{plugin_name}:{skill_name}",
            "",
            "# To re-publish after editing the skill, run `bbsctl publish` again",
            f"# and then `/plugin marketplace update {marketplace_name}` in Claude Code.",
        ]

        return PublishResult(
            success=True,
            target_name=self.name,
            artifacts={
                "marketplace.json": str(marketplace_json_path),
                "plugin.json": str(plugin_json_path),
                "marketplace_dir": str(marketplace_dir),
            },
            next_steps=next_steps,
        )


def _copy_skill_files(*, src: Path, dst: Path) -> None:
    """Copy SKILL.md plus the optional spec subdirectories (scripts/, references/, assets/)."""
    skill_md = src / "SKILL.md"
    if skill_md.exists():
        shutil.copy2(skill_md, dst / "SKILL.md")

    for subdir in ("scripts", "references", "assets"):
        src_sub = src / subdir
        if src_sub.exists() and src_sub.is_dir():
            dst_sub = dst / subdir
            if dst_sub.exists():
                shutil.rmtree(dst_sub)
            shutil.copytree(src_sub, dst_sub)


def _author_object(name: str | None, email: str | None) -> dict[str, str]:
    """Build the public-spec author object — `name` required, `email` optional."""
    out: dict[str, str] = {"name": name or "anonymous"}
    if email:
        out["email"] = email
    return out


def _detect_author_name() -> str:
    """Best-effort author name detection. Falls back to 'anonymous'."""
    import os

    return os.environ.get("USER") or os.environ.get("USERNAME") or "anonymous"


def _relativize_for_display(path: Path) -> str:
    """Return a path relative to CWD when possible, otherwise absolute.

    Quoting for shell safety: if the path contains spaces, wrap in quotes.
    """
    try:
        rel = path.relative_to(Path.cwd())
        display = f"./{rel}"
    except ValueError:
        display = str(path)
    if " " in display:
        display = f"'{display}'"
    return display


__all__ = ["ClaudeCodeLocalTarget"]
