"""Tests for the bundle module — bundle.lock + signature + verify."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillctl.marketplace.bundle import (
    BundleLock,
    compute_bundle_lock,
    verify_bundle,
    write_bundle_lock,
    write_bundle_signature_placeholder,
)


def _make_bundle(tmp_path: Path) -> Path:
    """Build a small bundle directory with a SKILL.md + skill.yaml + evals/."""
    bundle = tmp_path / "my-skill-bundle"
    bundle.mkdir()
    (bundle / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nbody",
                                      encoding="utf-8")
    (bundle / "skill.yaml").write_text("name: x\nstrictness: team\n", encoding="utf-8")
    (bundle / "evals").mkdir()
    (bundle / "evals" / "behavior.json").write_text(
        json.dumps({"skill_name": "x", "evals": []}), encoding="utf-8"
    )
    return bundle


# ── compute_bundle_lock ────────────────────────────────────────────────────


def test_compute_bundle_lock_includes_every_file(tmp_path):
    bundle = _make_bundle(tmp_path)
    lock = compute_bundle_lock(bundle, name="my-skill", version="1.0.0")
    assert "SKILL.md" in lock.files
    assert "skill.yaml" in lock.files
    assert "evals/behavior.json" in lock.files
    assert lock.bundle_name == "my-skill"
    assert lock.bundle_version == "1.0.0"


def test_compute_bundle_lock_excludes_self_and_sig(tmp_path):
    bundle = _make_bundle(tmp_path)
    # Pre-populate a stale lock + sig; they must not appear in the new lock.
    (bundle / "bundle.lock").write_text("stale", encoding="utf-8")
    (bundle / "bundle.sig").write_text("stale", encoding="utf-8")
    lock = compute_bundle_lock(bundle, name="x", version="0.0.1")
    assert "bundle.lock" not in lock.files
    assert "bundle.sig" not in lock.files


def test_compute_bundle_lock_skips_pycache_and_git(tmp_path):
    bundle = _make_bundle(tmp_path)
    (bundle / "__pycache__").mkdir()
    (bundle / "__pycache__" / "junk.pyc").write_bytes(b"x")
    (bundle / ".git").mkdir()
    (bundle / ".git" / "HEAD").write_bytes(b"x")
    lock = compute_bundle_lock(bundle, name="x", version="0.0.1")
    assert not any("__pycache__" in p for p in lock.files)
    assert not any(".git/" in p for p in lock.files)


def test_lock_is_byte_stable_for_signing(tmp_path):
    bundle = _make_bundle(tmp_path)
    lock_a = compute_bundle_lock(bundle, name="x", version="1.0.0")
    lock_b = compute_bundle_lock(bundle, name="x", version="1.0.0")
    assert lock_a.to_json() == lock_b.to_json()


def test_lock_serialization_round_trip(tmp_path):
    bundle = _make_bundle(tmp_path)
    lock = compute_bundle_lock(bundle, name="x", version="1.0.0")
    rt = BundleLock.from_json(lock.to_json())
    assert rt.bundle_name == lock.bundle_name
    assert rt.files == lock.files


# ── write_bundle_lock ──────────────────────────────────────────────────────


def test_write_bundle_lock_creates_file(tmp_path):
    bundle = _make_bundle(tmp_path)
    p = write_bundle_lock(bundle, name="x", version="0.1.0")
    assert p.exists()
    data = json.loads(p.read_text())
    assert "files" in data
    assert "SKILL.md" in data["files"]


# ── signature placeholder ──────────────────────────────────────────────────


def test_signature_requires_lock(tmp_path):
    bundle = _make_bundle(tmp_path)
    with pytest.raises(FileNotFoundError):
        write_bundle_signature_placeholder(bundle)


def test_signature_placeholder_references_lock_digest(tmp_path):
    bundle = _make_bundle(tmp_path)
    write_bundle_lock(bundle, name="x", version="0.1.0")
    sig_path = write_bundle_signature_placeholder(bundle)
    sig = json.loads(sig_path.read_text())
    assert sig["kind"] == "placeholder"
    assert "lock_digest" in sig
    assert len(sig["lock_digest"]) == 64  # sha256 hex


# ── verify_bundle ──────────────────────────────────────────────────────────


def test_verify_passes_on_unchanged_bundle(tmp_path):
    bundle = _make_bundle(tmp_path)
    write_bundle_lock(bundle, name="x", version="0.1.0")
    ok, errors = verify_bundle(bundle)
    assert ok
    assert errors == []


def test_verify_fails_when_lock_missing(tmp_path):
    bundle = _make_bundle(tmp_path)
    ok, errors = verify_bundle(bundle)
    assert not ok
    assert any("bundle.lock missing" in e for e in errors)


def test_verify_fails_on_tampered_file(tmp_path):
    bundle = _make_bundle(tmp_path)
    write_bundle_lock(bundle, name="x", version="0.1.0")
    # Tamper.
    (bundle / "SKILL.md").write_text("EVIL", encoding="utf-8")
    ok, errors = verify_bundle(bundle)
    assert not ok
    assert any("digest mismatch" in e for e in errors)


def test_verify_fails_on_missing_file(tmp_path):
    bundle = _make_bundle(tmp_path)
    write_bundle_lock(bundle, name="x", version="0.1.0")
    (bundle / "evals" / "behavior.json").unlink()
    ok, errors = verify_bundle(bundle)
    assert not ok
    assert any("missing file" in e for e in errors)


def test_verify_fails_on_unexpected_file(tmp_path):
    bundle = _make_bundle(tmp_path)
    write_bundle_lock(bundle, name="x", version="0.1.0")
    (bundle / "rogue.txt").write_text("smuggled", encoding="utf-8")
    ok, errors = verify_bundle(bundle)
    assert not ok
    assert any("unexpected file" in e for e in errors)


# ── GitMarketplace integration ─────────────────────────────────────────────


def test_git_marketplace_publish_writes_bundle_lock_and_sig(tmp_path):
    from skillctl.marketplace.git_marketplace import GitMarketplace

    skill = tmp_path / "src" / "my-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: test\n---\nbody", encoding="utf-8"
    )
    (skill / "skill.yaml").write_text(
        "name: my-skill\nstrictness: team\n", encoding="utf-8"
    )
    (skill / "permissions.yaml").write_text(
        "schema_version: bulbasaur/v1\nskill: my-skill\n", encoding="utf-8"
    )

    market_dir = tmp_path / "market"
    market = GitMarketplace.init(market_dir, name="test-market", owner_name="me")

    plugin_dir = market.publish_plugin(
        plugin_name="my-skill-plugin",
        skill_name="my-skill",
        skill_dir=skill,
        version="0.1.0",
        description="test",
        strictness="team",
    )
    # Marketplace layout copies the skill into the plugin's skills/ subdir.
    skill_in_plugin = plugin_dir / "skills" / "my-skill"
    assert (skill_in_plugin / "SKILL.md").exists()
    assert (skill_in_plugin / "permissions.yaml").exists()
    # Bundle lock + sig in plugin root.
    assert (plugin_dir / "bundle.lock").exists()
    assert (plugin_dir / "bundle.sig").exists()
    # Verify round-trip.
    ok, errors = market.verify_plugin("my-skill-plugin")
    assert ok, errors


def test_git_marketplace_verify_catches_post_publish_tamper(tmp_path):
    from skillctl.marketplace.git_marketplace import GitMarketplace

    skill = tmp_path / "src" / "my-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: x\n---\nbody", encoding="utf-8")

    market_dir = tmp_path / "market"
    market = GitMarketplace.init(market_dir)
    plugin_dir = market.publish_plugin(
        plugin_name="my-skill-plugin",
        skill_name="my-skill",
        skill_dir=skill,
    )
    # Tamper after publish.
    (plugin_dir / "skills" / "my-skill" / "SKILL.md").write_text(
        "TAMPERED", encoding="utf-8"
    )
    ok, errors = market.verify_plugin("my-skill-plugin")
    assert not ok
    assert any("digest mismatch" in e for e in errors)
