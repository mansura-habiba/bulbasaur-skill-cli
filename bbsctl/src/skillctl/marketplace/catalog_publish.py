"""In-place publish of a catalog artifact into a Claude Code marketplace.

For curation repos laid out as:

  - `.claude-plugin/marketplace.json` — Claude schema; ``source`` points at
    ``./artifacts/.../src`` (no file copy)
  - ``artifacts/<squad>/<team>/<slug>/marketplace-entry.json`` — sidecar entry

Regenerates marketplace entries from ``manifest.yml``.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.durable import atomic_write_json, file_lock
from skillctl.messaging import FrameworkError

_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CLAUDE_SCHEMA = "https://code.claude.com/schemas/marketplace.json"
_SIDECAR_SCHEMA = "bulbasaur/catalog-marketplace-entry/v1"
_DEFAULT_MARKETPLACE_NAME = "catalog"


class CatalogPublishError(Exception):
    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


def find_repo_root(start: Path) -> Path | None:
    """Walk up looking for a curation root (artifacts/ + .claude-plugin/)."""
    cur = start.resolve()
    for _ in range(20):
        if (cur / "artifacts").is_dir() and (cur / ".claude-plugin").is_dir():
            return cur
        if (cur / "artifacts").is_dir() and (cur / "marketplace.json").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def resolve_artifact_dir(path: Path) -> Path:
    """Accept artifact root or its ``src/`` directory."""
    path = path.resolve()
    if (path / "manifest.yml").is_file():
        return path
    if path.name == "src" and (path.parent / "manifest.yml").is_file():
        return path.parent
    if (path / "SKILL.md").is_file() and (path.parent / "manifest.yml").is_file():
        return path.parent
    raise CatalogPublishError(
        FrameworkError(
            summary=f"not a catalog artifact directory: {path}",
            detail="expected manifest.yml next to src/",
            fix=(
                "Pass artifacts/<squad>/<team>/<slug>, or a skill directory that "
                "contains manifest.yml alongside src/."
            ),
        )
    )


def load_manifest(artifact_dir: Path) -> dict[str, Any]:
    path = artifact_dir / "manifest.yml"
    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path)
    except Exception as exc:
        raise CatalogPublishError(
            FrameworkError(
                summary="manifest.yml: YAML parse error",
                detail=str(exc),
                fix="Fix YAML syntax in manifest.yml.",
            )
        ) from exc
    if not isinstance(raw, dict):
        raise CatalogPublishError(
            FrameworkError(
                summary="manifest.yml must be a mapping",
                fix="Use key: value pairs at the top level.",
            )
        )
    return raw


def publish_catalog_artifact(
    artifact_dir: Path,
    *,
    repo_root: Path | None = None,
    dry_run: bool = False,
    marketplace_name: str = _DEFAULT_MARKETPLACE_NAME,
) -> dict[str, Any]:
    """Upsert Claude marketplace entry + sidecar for one catalog artifact.

    Returns ``{name, claude_path, sidecar_path, source, marketplace_name, dry_run}``.
    """
    artifact_dir = resolve_artifact_dir(artifact_dir)
    root = repo_root or find_repo_root(artifact_dir)
    if root is None:
        raise CatalogPublishError(
            FrameworkError(
                summary="cannot find catalog curation repo root",
                detail="looked for artifacts/ + .claude-plugin/ above the artifact",
                fix=(
                    "Run from inside a curation repo (artifacts/ + .claude-plugin/), "
                    "or pass `--repo-root <path>`."
                ),
            )
        )

    manifest = load_manifest(artifact_dir)
    status = str(manifest.get("status") or "").strip().lower()
    if status and status not in {"active", ""}:
        raise CatalogPublishError(
            FrameworkError(
                summary=f"artifact status is `{status}` — not publishable",
                fix="Set `status: active` in manifest.yml.",
            )
        )

    name = str(manifest.get("name") or "").strip()
    if not name or not _KEBAB.match(name):
        raise CatalogPublishError(
            FrameworkError(
                summary=f"manifest name `{name}` must be kebab-case",
                fix="Use a name like `my-skill` (Claude Code plugin name rules).",
            )
        )

    claude_entry = build_claude_entry(manifest, artifact_dir, repo_root=root)
    if claude_entry is None:
        raise CatalogPublishError(
            FrameworkError(
                summary=f"cannot derive Claude marketplace layout for `{name}`",
                detail="no SKILL.md / .mcp.json under src/",
                fix="Add src/SKILL.md (layout A) or src/<dir>/SKILL.md (layout B).",
            )
        )

    sidecar = build_sidecar(manifest, claude_entry)
    claude_path = root / ".claude-plugin" / "marketplace.json"
    sidecar_path = artifact_dir / "marketplace-entry.json"
    mp_name = _read_marketplace_name(claude_path) or marketplace_name

    if dry_run:
        return {
            "name": name,
            "source": claude_entry.get("source"),
            "claude_path": str(claude_path),
            "sidecar_path": str(sidecar_path),
            "marketplace_name": mp_name,
            "entry": claude_entry,
            "dry_run": True,
        }

    claude_path.parent.mkdir(parents=True, exist_ok=True)
    upsert_plugin_entry(claude_path, claude_entry, marketplace_name=mp_name)
    if "updatedAt" not in sidecar and sidecar_path.is_file():
        try:
            prior = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if isinstance(prior, dict) and prior.get("updatedAt"):
                sidecar["updatedAt"] = prior["updatedAt"]
        except (OSError, json.JSONDecodeError):
            pass
    atomic_write_json(sidecar_path, sidecar)

    legacy = root / "marketplace.json"
    if legacy.exists():
        upsert_legacy_index(legacy, sidecar, sidecar_path.relative_to(root).as_posix())

    return {
        "name": name,
        "source": claude_entry.get("source"),
        "claude_path": str(claude_path),
        "sidecar_path": str(sidecar_path),
        "marketplace_name": mp_name,
        "dry_run": False,
    }


def build_claude_entry(
    manifest: dict[str, Any], artifact_dir: Path, *, repo_root: Path
) -> dict[str, Any] | None:
    layout = detect_layout(manifest, artifact_dir, repo_root=repo_root)
    if layout is None:
        return None
    bucket, source, skills_override = layout

    name = str(manifest["name"])
    owners = manifest.get("owners") or []
    keywords = [
        str(tag).split(":", 1)[-1].strip().lower()
        for tag in (manifest.get("tags") or [])
        if not str(tag).startswith("lifecycle:")
    ]

    entry: dict[str, Any] = {
        "name": name,
        "source": source,
        "description": _extract_description(artifact_dir, manifest),
        "version": str(manifest.get("version") or "0.1.0"),
    }
    title = manifest.get("title")
    if title and title != name:
        entry["displayName"] = title
    if owners:
        entry["author"] = {"name": str(owners[0]).lstrip("@")}
    blog = manifest.get("blog_post")
    if blog:
        entry["homepage"] = str(blog)
    if manifest.get("source_repo"):
        entry["repository"] = manifest["source_repo"]
    if keywords:
        entry["keywords"] = keywords
    if manifest.get("home_squad"):
        entry["category"] = manifest["home_squad"]
    license_ = (manifest.get("upstream") or {}).get("license")
    if license_:
        entry["license"] = license_
    if skills_override:
        entry["skills"] = skills_override
    if bucket == "M":
        entry["mcpServers"] = "./.mcp.json"
    entry["metadata"] = {
        "squad": manifest.get("home_squad"),
        "team": manifest.get("team"),
        "level": manifest.get("level"),
        "assetType": manifest.get("type"),
        "layout": bucket,
        "hosting": manifest.get("hosting", "local"),
        "claudeInstallable": bucket in {"A", "B", "C", "M"},
    }
    order = [
        "name",
        "displayName",
        "source",
        "description",
        "version",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "category",
        "skills",
        "mcpServers",
        "metadata",
    ]
    return {k: entry[k] for k in order if k in entry}


def detect_layout(
    manifest: dict[str, Any], artifact_dir: Path, *, repo_root: Path
) -> tuple[str, str, list[str] | None] | None:
    """Return (bucket, source_rel, skills_override) or None."""
    src = artifact_dir / "src"
    try:
        art_rel = "./" + artifact_dir.relative_to(repo_root).as_posix()
    except ValueError:
        art_rel = "./" + artifact_dir.name
    rel = f"{art_rel.rstrip('/')}/src"

    asset_type = str(manifest.get("type") or "skill").lower()
    if asset_type in {"mcp", "mcp-server"}:
        if (src / ".mcp.json").is_file():
            return ("M", rel, None)
        return None

    if not src.is_dir():
        return None

    if (src / "SKILL.md").is_file():
        return ("A", rel, None)

    skills_dir = src / "skills"
    if skills_dir.is_dir() and any(
        (d / "SKILL.md").is_file() for d in skills_dir.iterdir() if d.is_dir()
    ):
        return ("C", rel, None)

    nested = sorted(
        d.name for d in src.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()
    )
    if nested:
        return ("B", rel, [f"./{n}" for n in nested])
    return None


def build_sidecar(
    manifest: dict[str, Any],
    claude_entry: dict[str, Any],
) -> dict[str, Any]:
    tags = [str(t) for t in (manifest.get("tags") or [])]
    owners = [str(o) for o in (manifest.get("owners") or [])]
    keywords = claude_entry.get("keywords") or [
        t.split(":", 1)[-1] for t in tags if not t.startswith("lifecycle:")
    ]
    sidecar: dict[str, Any] = {
        "$schema": _SIDECAR_SCHEMA,
        "schemaVersion": "1.0.0",
        "name": manifest.get("name"),
        "title": manifest.get("title") or manifest.get("name"),
        "type": manifest.get("type") or "skill",
        "version": str(manifest.get("version") or "0.1.0"),
        "description": claude_entry.get("description") or "",
        "squad": manifest.get("home_squad"),
        "team": manifest.get("team"),
        "level": manifest.get("level"),
        "tags": tags,
        "owners": owners,
        "hosting": manifest.get("hosting", "local"),
        "sourceRepo": manifest.get("source_repo"),
        "blogPost": manifest.get("blog_post"),
        "skills": claude_entry.get("skills") or [],
        "keywords": keywords,
        "strict": False,
        "defaultEnabled": False,
    }
    if manifest.get("updated"):
        sidecar["updatedAt"] = str(manifest["updated"])
    return sidecar


def upsert_plugin_entry(
    marketplace_path: Path, entry: dict[str, Any], *, marketplace_name: str
) -> None:
    with file_lock(marketplace_path):
        if marketplace_path.exists():
            data = json.loads(marketplace_path.read_text(encoding="utf-8"))
        else:
            data = {
                "$schema": _CLAUDE_SCHEMA,
                "name": marketplace_name,
                "description": "Curated agentic asset catalog.",
                "version": "1.0.0",
                "owner": {"name": "catalog"},
                "plugins": [],
            }
        if not data.get("name"):
            data["name"] = marketplace_name
        plugins = list(data.get("plugins") or [])
        name = entry["name"]
        plugins = [p for p in plugins if p.get("name") != name]
        plugins.append(entry)
        plugins.sort(key=lambda p: str(p.get("name") or ""))
        data["plugins"] = plugins
        atomic_write_json(marketplace_path, data)


def upsert_legacy_index(
    index_path: Path, sidecar: dict[str, Any], sidecar_rel: str
) -> None:
    with file_lock(index_path):
        data = json.loads(index_path.read_text(encoding="utf-8"))
        entries = list(data.get("entries") or [])
        name = sidecar.get("name")
        new_entry = {
            "name": name,
            "title": sidecar.get("title"),
            "type": sidecar.get("type"),
            "version": sidecar.get("version"),
            "description": sidecar.get("description"),
            "tags": sidecar.get("tags") or [],
            "sidecarPath": sidecar_rel,
        }
        prior = next((e for e in entries if e.get("name") == name), None)
        entries = [e for e in entries if e.get("name") != name]
        entries.append(new_entry)
        entries.sort(key=lambda e: str(e.get("name") or ""))
        if prior != new_entry or data.get("entries") != entries:
            data["generatedAt"] = datetime.now(UTC).isoformat()
        data["entries"] = entries
        data["count"] = len(entries)
        atomic_write_json(index_path, data)


def _read_marketplace_name(marketplace_path: Path) -> str | None:
    if not marketplace_path.is_file():
        return None
    try:
        data = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return str(name) if name else None


def _extract_description(artifact_dir: Path, manifest: dict[str, Any]) -> str:
    readme = artifact_dir / "README.md"
    if readme.is_file():
        para: list[str] = []
        for raw in readme.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                if para:
                    break
                continue
            if line.startswith(("#", ">", "|", "-", "*", "```", "![", ":::", "<!--")):
                if para:
                    break
                continue
            para.append(line)
        if para:
            text = " ".join(para)
            text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
            text = re.sub(r"[*_`]", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            if text and not text.lower().startswith("migrated from"):
                return text if len(text) <= 200 else text[:197].rstrip() + "..."

    skill_md = artifact_dir / "src" / "SKILL.md"
    if skill_md.is_file():
        fm = _skill_frontmatter(skill_md)
        desc = fm.get("description")
        if isinstance(desc, str) and desc.strip():
            text = re.sub(r"\s+", " ", desc).strip()
            return text if len(text) <= 200 else text[:197].rstrip() + "..."

    return str(manifest.get("title") or manifest.get("name") or "")


def _skill_frontmatter(skill_md: Path) -> dict[str, Any]:
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    block: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        block.append(line)
    yaml = YAML(typ="safe")
    try:
        fm = yaml.load("\n".join(block))
    except Exception:
        return {}
    return fm if isinstance(fm, dict) else {}


__all__ = [
    "CatalogPublishError",
    "find_repo_root",
    "publish_catalog_artifact",
    "resolve_artifact_dir",
]
