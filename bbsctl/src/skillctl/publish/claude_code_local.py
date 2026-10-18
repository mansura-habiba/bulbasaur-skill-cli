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
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from skillctl import __version__
from skillctl.durable import atomic_write_json, purge_stale_markers, replace_directory

from .target import PublishContext, PublishResult, PublishTarget

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

        plugins_root = marketplace_dir / "plugins"
        plugins_root.mkdir(parents=True, exist_ok=True)
        purge_stale_markers(plugins_root)
        plugin_dir = plugins_root / plugin_name
        marketplace_meta_dir = marketplace_dir / ".claude-plugin"
        marketplace_meta_dir.mkdir(parents=True, exist_ok=True)

        staging = Path(
            tempfile.mkdtemp(prefix=f".{plugin_name}.", dir=str(plugins_root))
        )
        try:
            skill_target_dir = staging / "skills" / skill_name
            plugin_meta_dir = staging / ".claude-plugin"
            skill_target_dir.mkdir(parents=True, exist_ok=True)
            plugin_meta_dir.mkdir(parents=True, exist_ok=True)

            _copy_skill_files(src=context.skill_dir, dst=skill_target_dir)

            plugin_manifest = {
                "name": plugin_name,
                "version": "0.1.0",
                "description": context.frontmatter.description or "",
                "author": _author_object(author_name, author_email),
            }
            plugin_json_path = plugin_meta_dir / "plugin.json"
            atomic_write_json(plugin_json_path, plugin_manifest)
            replace_directory(staging, plugin_dir)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        marketplace_json_path = marketplace_meta_dir / "marketplace.json"
        entry = {
            "name": plugin_name,
            "source": f"./plugins/{plugin_name}",
            "description": context.frontmatter.description or "",
            "version": "0.1.0",
        }
        data = _load_or_seed_marketplace(
            marketplace_json_path,
            marketplace_name=marketplace_name,
            author_name=author_name,
            author_email=author_email,
            strictness=context.strictness.value,
        )
        plugins = [p for p in (data.get("plugins") or []) if p.get("name") != plugin_name]
        plugins.append(entry)
        plugins.sort(key=lambda p: str(p.get("name") or ""))
        data["plugins"] = plugins
        data.setdefault("metadata", {})["generated_by"] = f"skillctl {__version__}"
        data["metadata"]["strictness"] = context.strictness.value
        atomic_write_json(marketplace_json_path, data)

        rel_marketplace = _relativize_for_display(marketplace_dir)
        next_steps = [
            "# 1. In Claude Code, add this marketplace:",
            f"/plugin marketplace add {rel_marketplace}",
            "",
            "# 2. Install the plugin from the marketplace:",
            f"/plugin install {plugin_name}@{marketplace_name}",
            "",
            "# 3. Invoke the skill (Claude Code namespaces plugin skills as plugin:skill):",
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
                "plugin.json": str(plugin_dir / ".claude-plugin" / "plugin.json"),
                "marketplace_dir": str(marketplace_dir),
            },
            next_steps=next_steps,
        )


def _load_or_seed_marketplace(
    path: Path,
    *,
    marketplace_name: str,
    author_name: str,
    author_email: str | None,
    strictness: str,
) -> dict:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "name": marketplace_name,
        "owner": _author_object(author_name, author_email),
        "description": "Bulbasaur-published skills (local marketplace).",
        "plugins": [],
        "metadata": {
            "generated_by": f"skillctl {__version__}",
            "strictness": strictness,
        },
    }


def _copy_skill_files(*, src: Path, dst: Path) -> None:
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
    out: dict[str, str] = {"name": name or "anonymous"}
    if email:
        out["email"] = email
    return out


def _detect_author_name() -> str:
    import os

    return os.environ.get("USER") or os.environ.get("USERNAME") or "anonymous"


def _relativize_for_display(path: Path) -> str:
    try:
        rel = path.relative_to(Path.cwd())
        display = f"./{rel}"
    except ValueError:
        display = str(path)
    if " " in display:
        display = f"'{display}'"
    return display


__all__ = ["ClaudeCodeLocalTarget"]
