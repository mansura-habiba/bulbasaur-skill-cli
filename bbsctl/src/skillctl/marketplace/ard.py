"""Emit ARD (Agentic Resource Discovery) manifests for skills.

ARD is a federated discovery envelope — find resources before invoke.
It is not an install runtime and does not replace Claude / catalog marketplace
packaging. See https://agenticresourcediscovery.org/

bbsctl only *emits* `ard.json` from SKILL.md / catalog manifest.yml.
It does not run an ARD search registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.durable import atomic_write_json
from skillctl.messaging import FrameworkError

# Spec community type for Markdown agent skills (ARD v0.91).
_SKILL_TYPE = "application/agent-skills+md"
_DEFAULT_DOMAIN = "local"


class ArdEmitError(Exception):
    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


def skill_to_ard_entry(
    skill_dir: Path,
    *,
    domain: str = _DEFAULT_DOMAIN,
    url: str | None = None,
    queries: list[str] | None = None,
) -> dict[str, Any]:
    """Build one ARD entry from a skill directory (SKILL.md required)."""
    skill_dir = skill_dir.resolve()
    skill_md = _find_skill_md(skill_dir)
    if skill_md is None:
        raise ArdEmitError(
            FrameworkError(
                summary=f"SKILL.md not found under {skill_dir}",
                fix="Pass a skill directory containing SKILL.md.",
            )
        )

    fm = _frontmatter(skill_md)
    name = str(fm.get("name") or skill_dir.name).strip()
    description = str(fm.get("description") or "").strip()
    if not name:
        raise ArdEmitError(
            FrameworkError(
                summary="skill frontmatter missing `name`",
                fix="Add `name:` to SKILL.md frontmatter.",
            )
        )

    identifier = f"urn:air:{_sanitize_domain(domain)}:skill:{name}"
    entry_url = url or skill_md.resolve().as_uri()
    rep_queries = queries or _default_queries(name, description, skill_md)

    entry: dict[str, Any] = {
        "identifier": identifier,
        "displayName": name,
        "type": _SKILL_TYPE,
        "url": entry_url,
        "description": description or f"Agent skill `{name}`",
        "representativeQueries": rep_queries[:5],
    }
    # Optional capabilities from catalog tags when present
    caps = _capabilities_from_manifest(skill_dir)
    if caps:
        entry["capabilities"] = caps
    return entry


def artifact_to_ard_entry(
    artifact_dir: Path,
    *,
    domain: str = _DEFAULT_DOMAIN,
    url: str | None = None,
    queries: list[str] | None = None,
) -> dict[str, Any]:
    """Build an ARD entry from a catalog artifact folder (manifest.yml + src/)."""
    artifact_dir = artifact_dir.resolve()
    manifest_path = artifact_dir / "manifest.yml"
    if not manifest_path.is_file():
        return skill_to_ard_entry(
            artifact_dir, domain=domain, url=url, queries=queries
        )

    yaml = YAML(typ="safe")
    try:
        manifest = yaml.load(manifest_path)
    except Exception as exc:
        raise ArdEmitError(
            FrameworkError(
                summary="manifest.yml: YAML parse error",
                detail=str(exc),
                fix="Fix YAML syntax in manifest.yml.",
            )
        ) from exc
    if not isinstance(manifest, dict):
        raise ArdEmitError(
            FrameworkError(
                summary="manifest.yml must be a mapping",
                fix="Use key: value pairs at the top level.",
            )
        )

    name = str(manifest.get("name") or artifact_dir.name).strip()
    title = str(manifest.get("title") or name)
    description = str(manifest.get("description") or title)
    # Prefer README / SKILL description when present
    skill_md = _find_skill_md(artifact_dir)
    if skill_md is not None:
        fm = _frontmatter(skill_md)
        if fm.get("description"):
            description = str(fm["description"]).strip()

    entry_url = url or (
        str(manifest.get("source_repo") or "").strip()
        or (skill_md.resolve().as_uri() if skill_md else artifact_dir.as_uri())
    )
    rep_queries = queries or _default_queries(name, description, skill_md)

    entry: dict[str, Any] = {
        "identifier": f"urn:air:{_sanitize_domain(domain)}:skill:{name}",
        "displayName": title,
        "type": _SKILL_TYPE,
        "url": entry_url,
        "description": description,
        "representativeQueries": rep_queries[:5],
    }
    tags = manifest.get("tags") or []
    caps = [
        str(t).split(":", 1)[-1]
        for t in tags
        if str(t).startswith(("capability:", "domain:"))
    ]
    if caps:
        entry["capabilities"] = caps
    return entry


def write_ard_manifest(
    entries: list[dict[str, Any]],
    output: Path,
    *,
    upsert: bool = True,
) -> Path:
    """Write or merge entries into an ard.json file."""
    output = output.resolve()
    existing: list[dict[str, Any]] = []
    if upsert and output.is_file():
        try:
            data = json.loads(output.read_text(encoding="utf-8"))
            existing = list(data.get("entries") or [])
        except (OSError, json.JSONDecodeError):
            existing = []

    by_id = {e.get("identifier"): e for e in existing if e.get("identifier")}
    for entry in entries:
        by_id[entry["identifier"]] = entry

    payload = {
        "entries": sorted(by_id.values(), key=lambda e: str(e.get("identifier") or "")),
    }
    atomic_write_json(output, payload)
    return output


def catalog_to_ard_entries(
    catalog_root: Path,
    *,
    domain: str = _DEFAULT_DOMAIN,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Walk artifacts/ and emit one ARD entry per active skill."""
    catalog_root = catalog_root.resolve()
    entries: list[dict[str, Any]] = []
    for manifest in sorted(catalog_root.rglob("manifest.yml")):
        artifact = manifest.parent
        yaml = YAML(typ="safe")
        try:
            raw = yaml.load(manifest)
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "active").lower()
        if status not in {"active", ""}:
            continue
        asset_type = str(raw.get("type") or "").lower()
        if asset_type not in {"skill", "plugin", ""}:
            continue
        url = None
        if base_url:
            try:
                rel = artifact.relative_to(catalog_root).as_posix()
                url = f"{base_url.rstrip('/')}/{rel}/src/SKILL.md"
            except ValueError:
                url = base_url
        try:
            entries.append(
                artifact_to_ard_entry(artifact, domain=domain, url=url)
            )
        except ArdEmitError:
            continue
    return entries


def _find_skill_md(root: Path) -> Path | None:
    direct = root / "SKILL.md"
    if direct.is_file():
        return direct
    nested = root / "src" / "SKILL.md"
    if nested.is_file():
        return nested
    matches = sorted(root.rglob("SKILL.md"))
    return matches[0] if matches else None


def _frontmatter(skill_md: Path) -> dict[str, Any]:
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


def _default_queries(name: str, description: str, skill_md: Path | None) -> list[str]:
    queries: list[str] = []
    if description:
        # First sentence-ish of description
        first = re.split(r"[.!?]\s+", description, maxsplit=1)[0].strip()
        if first:
            queries.append(first if first.endswith("?") else f"help me {first.lower()}")
    queries.append(f"use the {name} skill")
    queries.append(f"when should I use {name}")
    if skill_md is not None:
        body = skill_md.read_text(encoding="utf-8")
        for match in re.finditer(
            r"(?:When to use|Use when|Triggers?)[^\n]*\n((?:[-*].*\n)+)",
            body,
            re.IGNORECASE,
        ):
            for line in match.group(1).splitlines():
                bullet = re.sub(r"^[-*]\s+", "", line).strip()
                if bullet and len(queries) < 5:
                    queries.append(bullet)
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out[:5] or [f"use {name}"]


def _capabilities_from_manifest(skill_dir: Path) -> list[str]:
    for candidate in (skill_dir / "manifest.yml", skill_dir.parent / "manifest.yml"):
        if not candidate.is_file():
            continue
        yaml = YAML(typ="safe")
        try:
            raw = yaml.load(candidate)
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        tags = raw.get("tags") or []
        return [
            str(t).split(":", 1)[-1]
            for t in tags
            if str(t).startswith("capability:")
        ]
    return []


def _sanitize_domain(domain: str) -> str:
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0]
    d = re.sub(r"[^a-z0-9.-]", "-", d)
    return d or _DEFAULT_DOMAIN


__all__ = [
    "ArdEmitError",
    "artifact_to_ard_entry",
    "catalog_to_ard_entries",
    "skill_to_ard_entry",
    "write_ard_manifest",
]
