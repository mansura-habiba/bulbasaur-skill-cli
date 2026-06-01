"""Bundle lock + signature — the content-addressed publish artifact.

Per the skill-lifecycle whitepaper, a published skill bundle is a directory
that includes SKILL.md, skill.yaml, permissions.yaml, ownership.yaml,
references/, evals/, plus the dist/ reports. `bundle.lock` is a SHA-256
digest per file; `bundle.sig` is a Sigstore signature over bundle.lock
(Phase 3+ — today we ship a placeholder so the format is forward-compatible).

The GitMarketplace's publish_plugin writes bundle.lock automatically when
publishing at team+ strictness; downstream `bbsctl install` verifies the
lock against the on-disk contents before installing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

_BUNDLE_LOCK_NAME = "bundle.lock"
_BUNDLE_SIG_NAME = "bundle.sig"
_BUNDLE_SCHEMA_VERSION = "bulbasaur/v1"

# Files NEVER included in the lock (transient, build artifacts, signing).
_LOCK_EXCLUDE = {
    "bundle.lock",
    "bundle.sig",
    ".DS_Store",
}
# Directories never traversed.
_LOCK_EXCLUDE_DIRS = {"__pycache__", ".git"}


@dataclass
class BundleLock:
    """Content-addressed digest of every file in a bundle.

    Files are keyed by their POSIX-style relative path from the bundle root.
    Sorted at serialization so the JSON is byte-stable for signing.
    """

    schema_version: str = _BUNDLE_SCHEMA_VERSION
    bundle_name: str = ""
    bundle_version: str = ""
    files: dict[str, str] = field(default_factory=dict)  # path → sha256

    def to_json(self) -> str:
        """Stable JSON serialization for signing."""
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "bundle_name": self.bundle_name,
                "bundle_version": self.bundle_version,
                "files": dict(sorted(self.files.items())),
            },
            indent=2,
            sort_keys=False,  # preserve top-level key order
        )

    @classmethod
    def from_json(cls, text: str) -> BundleLock:
        data = json.loads(text)
        return cls(
            schema_version=str(data.get("schema_version") or _BUNDLE_SCHEMA_VERSION),
            bundle_name=str(data.get("bundle_name") or ""),
            bundle_version=str(data.get("bundle_version") or ""),
            files=dict(data.get("files") or {}),
        )


def compute_bundle_lock(
    bundle_dir: Path, *, name: str, version: str
) -> BundleLock:
    """Walk `bundle_dir` and compute SHA-256 for every file.

    Files are recorded with POSIX-style relative paths from `bundle_dir`.
    Excludes the lock and signature files (they are emitted after).
    """
    files: dict[str, str] = {}
    for path in _walk(bundle_dir):
        rel = path.relative_to(bundle_dir).as_posix()
        files[rel] = _sha256_file(path)
    return BundleLock(
        bundle_name=name,
        bundle_version=version,
        files=files,
    )


def write_bundle_lock(
    bundle_dir: Path, *, name: str, version: str
) -> Path:
    """Compute and write `bundle.lock` to the bundle directory.

    Returns the path written. Overwrites any existing lock.
    """
    lock = compute_bundle_lock(bundle_dir, name=name, version=version)
    lock_path = bundle_dir / _BUNDLE_LOCK_NAME
    lock_path.write_text(lock.to_json(), encoding="utf-8")
    return lock_path


def write_bundle_signature_placeholder(bundle_dir: Path) -> Path:
    """Write a placeholder `bundle.sig` so the bundle layout is complete.

    Today we ship a placeholder; Phase 3 wires Sigstore. The placeholder is
    a small JSON `{schema_version, kind: "placeholder", lock_digest}` so the
    next phase can replace it without changing the file's role.
    """
    lock_path = bundle_dir / _BUNDLE_LOCK_NAME
    if not lock_path.exists():
        raise FileNotFoundError(
            f"cannot sign: {lock_path} does not exist. "
            "Call write_bundle_lock first."
        )
    lock_digest = _sha256_file(lock_path)
    sig_payload = {
        "schema_version": _BUNDLE_SCHEMA_VERSION,
        "kind": "placeholder",
        "lock_digest": lock_digest,
        "note": "Sigstore signing wires in Phase 3 of the bbsctl roadmap.",
    }
    sig_path = bundle_dir / _BUNDLE_SIG_NAME
    sig_path.write_text(
        json.dumps(sig_payload, indent=2), encoding="utf-8"
    )
    return sig_path


def verify_bundle(bundle_dir: Path) -> tuple[bool, list[str]]:
    """Verify on-disk bundle contents against `bundle.lock`.

    Returns (ok, errors). `ok=True` iff every file in the lock exists on disk
    with the recorded digest and no unexpected files are present (excluding
    the lock and signature themselves).
    """
    lock_path = bundle_dir / _BUNDLE_LOCK_NAME
    if not lock_path.exists():
        return False, [f"{_BUNDLE_LOCK_NAME} missing"]

    try:
        lock = BundleLock.from_json(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"{_BUNDLE_LOCK_NAME} unreadable: {exc}"]

    errors: list[str] = []
    actual_files: set[str] = set()
    for path in _walk(bundle_dir):
        rel = path.relative_to(bundle_dir).as_posix()
        actual_files.add(rel)
        expected = lock.files.get(rel)
        if expected is None:
            errors.append(f"unexpected file (not in lock): {rel}")
            continue
        actual = _sha256_file(path)
        if actual != expected:
            errors.append(
                f"digest mismatch: {rel} expected {expected[:12]}... got {actual[:12]}..."
            )

    missing = set(lock.files.keys()) - actual_files
    for m in sorted(missing):
        errors.append(f"missing file (in lock): {m}")

    return (not errors), errors


def _walk(root: Path):
    """Yield every file under `root`, sorted, excluding lock/sig and cruft."""
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in _LOCK_EXCLUDE:
            continue
        if any(part in _LOCK_EXCLUDE_DIRS for part in path.parts):
            continue
        paths.append(path)
    paths.sort()
    yield from paths


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


__all__ = [
    "BundleLock",
    "compute_bundle_lock",
    "verify_bundle",
    "write_bundle_lock",
    "write_bundle_signature_placeholder",
]
