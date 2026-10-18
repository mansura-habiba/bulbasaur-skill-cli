"""Evidence bundle assembly + verify."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skillctl.durable import atomic_write_json, purge_stale_markers, replace_directory
from skillctl.eval.reproducibility import compute_skill_hash
from skillctl.git_provenance import detect_git_provenance
from skillctl.marketplace.bundle import (
    compute_bundle_lock,
    verify_bundle,
    write_bundle_lock,
    write_bundle_signature_placeholder,
)
from skillctl.messaging import FrameworkError
from skillctl.lifecycle.result import StageResult
from skillctl.strictness import Strictness

_SCHEMA = "bulbasaur/v1"
_EVIDENCE_ROOT = ".bbsctl/evidence"


@dataclass
class EvidenceManifest:
    schema_version: str = _SCHEMA
    skill_name: str = ""
    skill_hash: str = ""
    git_commit: str = ""
    strictness: str = ""
    engines: dict[str, dict[str, str]] = field(default_factory=dict)
    model_ids: dict[str, str] = field(default_factory=dict)
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)  # rel path → sha256
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "skill_name": self.skill_name,
            "skill_hash": self.skill_hash,
            "git_commit": self.git_commit,
            "strictness": self.strictness,
            "engines": self.engines,
            "model_ids": self.model_ids,
            "stages": self.stages,
            "files": dict(sorted(self.files.items())),
            "created_at": self.created_at,
        }

    def digest(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evidence_dir_for(skill_dir: Path, skill_hash: str | None = None) -> Path:
    h = skill_hash or compute_skill_hash(skill_dir)
    name = skill_dir.name
    return skill_dir / _EVIDENCE_ROOT / f"{name}-{h[:12]}"


def assemble_evidence(
    skill_dir: Path,
    *,
    results: list[StageResult],
    strictness: Strictness,
) -> Path:
    """Collect stage artifacts into an evidence bundle and write lock + placeholder sig.

    Builds into a staging directory then atomically replaces the live bundle so a
    crash never leaves a half-written tree as `.bbsctl/evidence/<skill>-<hash>/`.
    """
    skill_hash = compute_skill_hash(skill_dir)
    evidence_root = skill_dir / _EVIDENCE_ROOT
    evidence_root.mkdir(parents=True, exist_ok=True)
    purge_stale_markers(evidence_root)
    bundle = evidence_dir_for(skill_dir, skill_hash)

    # Keep prior created_at + approval when re-assembling the same skill hash
    # so a double-run converges instead of churning timestamps / wiping sign-off.
    prior_created = ""
    prior_approval: dict[str, Any] | None = None
    if bundle.is_dir():
        try:
            prior_raw = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            prior_created = str(prior_raw.get("created_at") or "")
        except (OSError, json.JSONDecodeError):
            prior_created = ""
        approval_path = bundle / "approval.json"
        if approval_path.is_file():
            try:
                prior_approval = json.loads(approval_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prior_approval = None

    staging = Path(
        tempfile.mkdtemp(prefix=f".{bundle.name}.", dir=str(evidence_root))
    )
    try:
        prov = detect_git_provenance(skill_dir)
        manifest = EvidenceManifest(
            skill_name=skill_dir.name,
            skill_hash=skill_hash,
            git_commit=prov.commit_sha or "",
            strictness=strictness.value,
            created_at=prior_created or datetime.now(UTC).isoformat(),
        )

        for result in results:
            manifest.stages[result.stage] = {
                "status": result.status.value,
                "cached": result.cached,
                "duration_ms": result.duration_ms,
                "engine": result.engine.to_dict(),
            }
            if result.engine.name:
                manifest.engines[result.engine.name] = {
                    "version": result.engine.version,
                    "revision": result.engine.revision,
                }
            for art_name, art_path in result.artifacts.items():
                src = Path(art_path)
                if not src.is_file():
                    continue
                if art_name.startswith("certification/") or art_name.startswith(
                    "certification"
                ):
                    dest_rel = (
                        art_name if "/" in art_name else f"certification/{src.name}"
                    )
                else:
                    dest_rel = art_name
                dest = staging / dest_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

        for path in sorted(staging.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(staging).as_posix()
            if rel in {"bundle.lock", "bundle.sig", "manifest.json", "approval.json"}:
                continue
            manifest.files[rel] = _sha256_file(path)

        atomic_write_json(staging / "manifest.json", manifest.to_dict())
        write_bundle_lock(staging, name=skill_dir.name, version=skill_hash[:12])
        write_bundle_signature_placeholder(staging)

        digest = manifest.digest()
        if (
            prior_approval
            and prior_approval.get("skill_hash") == skill_hash
            and prior_approval.get("manifest_digest") == digest
        ):
            atomic_write_json(staging / "approval.json", prior_approval)
            write_bundle_lock(staging, name=skill_dir.name, version=skill_hash[:12])
            write_bundle_signature_placeholder(staging)

        replace_directory(staging, bundle)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return bundle


def write_approval(
    bundle_dir: Path,
    *,
    by: str,
    note: str = "",
) -> Path:
    """Write approval.json covering the current manifest digest.

    Idempotent: if an approval already covers this digest with the same
    approver and note, leave the file (and lock) unchanged.
    """
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise FrameworkError(
            summary="cannot approve: evidence manifest missing",
            detail=f"expected {manifest_path}",
            fix="Run `bbsctl pipeline` (or stages through certify) to assemble an evidence bundle first.",
            docs="../docs/lifecycle.md",
        )
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = EvidenceManifest(
        schema_version=str(raw.get("schema_version") or _SCHEMA),
        skill_name=str(raw.get("skill_name") or ""),
        skill_hash=str(raw.get("skill_hash") or ""),
        git_commit=str(raw.get("git_commit") or ""),
        strictness=str(raw.get("strictness") or ""),
        engines=dict(raw.get("engines") or {}),
        model_ids=dict(raw.get("model_ids") or {}),
        stages=dict(raw.get("stages") or {}),
        files=dict(raw.get("files") or {}),
        created_at=str(raw.get("created_at") or ""),
    )
    digest = manifest.digest()
    path = bundle_dir / "approval.json"
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("approver") == by
            and existing.get("note") == note
            and existing.get("manifest_digest") == digest
            and existing.get("skill_hash") == manifest.skill_hash
        ):
            return path

    payload = {
        "schema_version": _SCHEMA,
        "approver": by,
        "note": note,
        "timestamp": datetime.now(UTC).isoformat(),
        "manifest_digest": digest,
        "skill_hash": manifest.skill_hash,
    }
    atomic_write_json(path, payload)
    write_bundle_lock(
        bundle_dir,
        name=manifest.skill_name or bundle_dir.name,
        version=manifest.skill_hash[:12],
    )
    write_bundle_signature_placeholder(bundle_dir)
    return path


def verify_evidence(bundle_dir: Path, *, skill_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Recompute digests; check approval covers manifest; optionally check skill hash."""
    errors: list[str] = []
    ok_lock, lock_errors = verify_bundle(bundle_dir)
    if not ok_lock:
        errors.extend(lock_errors)

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append("manifest.json missing")
        return False, errors

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"manifest.json unreadable: {exc}")
        return False, errors

    # Recompute file digests listed in manifest.files
    for rel, expected in (raw.get("files") or {}).items():
        path = bundle_dir / rel
        if not path.is_file():
            errors.append(f"missing evidence file: {rel}")
            continue
        actual = _sha256_file(path)
        if actual != expected:
            errors.append(f"digest mismatch: {rel}")

    approval_path = bundle_dir / "approval.json"
    if approval_path.exists():
        try:
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"approval.json unreadable: {exc}")
        else:
            manifest = EvidenceManifest(
                schema_version=str(raw.get("schema_version") or _SCHEMA),
                skill_name=str(raw.get("skill_name") or ""),
                skill_hash=str(raw.get("skill_hash") or ""),
                git_commit=str(raw.get("git_commit") or ""),
                strictness=str(raw.get("strictness") or ""),
                engines=dict(raw.get("engines") or {}),
                model_ids=dict(raw.get("model_ids") or {}),
                stages=dict(raw.get("stages") or {}),
                files=dict(raw.get("files") or {}),
                created_at=str(raw.get("created_at") or ""),
            )
            if approval.get("manifest_digest") != manifest.digest():
                errors.append("approval.json does not cover current manifest digest")
            if skill_dir is not None:
                current = compute_skill_hash(skill_dir)
                if current != raw.get("skill_hash"):
                    errors.append(
                        "skill hash changed since evidence was assembled "
                        f"(evidence={str(raw.get('skill_hash'))[:12]}… "
                        f"current={current[:12]}…)"
                    )
                if current != approval.get("skill_hash"):
                    errors.append("approval skill_hash does not match current SKILL.md")

    return (not errors), errors


def latest_evidence_bundle(skill_dir: Path) -> Path | None:
    root = skill_dir / _EVIDENCE_ROOT
    if not root.is_dir():
        return None
    candidates = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


__all__ = [
    "EvidenceManifest",
    "assemble_evidence",
    "evidence_dir_for",
    "latest_evidence_bundle",
    "verify_evidence",
    "write_approval",
]
