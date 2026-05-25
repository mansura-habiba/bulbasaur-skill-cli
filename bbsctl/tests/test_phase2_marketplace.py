"""Tests for Phase 2 marketplace module (GitMarketplace + LockFile)."""

from __future__ import annotations

from pathlib import Path

from skillctl.marketplace.git_marketplace import GitMarketplace, MarketplaceNotFoundError
from skillctl.marketplace.lock import LockPlugin, load_lock, write_lock


# ── GitMarketplace ────────────────────────────────────────────────────────────

def test_init_creates_structure(tmp_path: Path) -> None:
    mp = GitMarketplace.init(tmp_path / "marketplace", name="test-mp")
    assert (mp.root / ".claude-plugin" / "marketplace.json").exists()
    assert (mp.root / "plugins").is_dir()
    assert mp.name == "test-mp"


def test_init_is_idempotent(tmp_path: Path) -> None:
    mp_dir = tmp_path / "marketplace"
    GitMarketplace.init(mp_dir, name="test-mp")
    GitMarketplace.init(mp_dir, name="test-mp")  # second call should not raise
    mp = GitMarketplace(mp_dir)
    assert mp.list_plugins() == []


def test_publish_plugin(tmp_path: Path) -> None:
    # Create a skill directory.
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Generates a report.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (skill_dir / "skill.yaml").write_text(
        "name: my-skill\nstrictness: team\n", encoding="utf-8"
    )

    mp = GitMarketplace.init(tmp_path / "marketplace", name="team-mp")
    plugin_dir = mp.publish_plugin(
        plugin_name="my-skill-plugin",
        skill_name="my-skill",
        skill_dir=skill_dir,
        description="Test skill",
        strictness="team",
    )
    assert plugin_dir.exists()
    assert (plugin_dir / ".claude-plugin" / "plugin.json").exists()
    assert (plugin_dir / "skills" / "my-skill" / "SKILL.md").exists()

    plugins = mp.list_plugins()
    assert len(plugins) == 1
    assert plugins[0].name == "my-skill-plugin"
    assert plugins[0].strictness == "team"


def test_resolve_plugin_returns_none_for_missing(tmp_path: Path) -> None:
    mp = GitMarketplace.init(tmp_path / "mp", name="mp")
    assert mp.resolve_plugin("nonexistent") is None


def test_marketplace_not_found_error_on_missing_dir(tmp_path: Path) -> None:
    mp = GitMarketplace(tmp_path / "nonexistent")
    assert not mp.exists()


# ── LockFile ─────────────────────────────────────────────────────────────────

def test_empty_lockfile_round_trip(tmp_path: Path) -> None:
    from skillctl.marketplace.lock import LockFile
    lock = LockFile()
    write_lock(lock, tmp_path)
    reloaded = load_lock(tmp_path)
    assert reloaded.plugins == []
    assert reloaded.version == 1


def test_add_and_remove_plugin(tmp_path: Path) -> None:
    lock = load_lock(tmp_path)
    lock.add_or_update_plugin(
        LockPlugin(
            name="test-skill",
            version="1.0.0",
            strictness="team",
            digest="sha256:abc",
            source="./mp#test-skill@1.0.0",
        )
    )
    write_lock(lock, tmp_path)

    reloaded = load_lock(tmp_path)
    assert reloaded.get_plugin("test-skill") is not None

    reloaded.remove_plugin("test-skill")
    write_lock(reloaded, tmp_path)

    final = load_lock(tmp_path)
    assert final.get_plugin("test-skill") is None


def test_upsert_updates_existing(tmp_path: Path) -> None:
    lock = load_lock(tmp_path)
    lock.add_or_update_plugin(
        LockPlugin("p", "1.0.0", "local", "sha256:old", "./mp#p@1.0.0")
    )
    lock.add_or_update_plugin(
        LockPlugin("p", "2.0.0", "team", "sha256:new", "./mp#p@2.0.0")
    )
    assert len(lock.plugins) == 1
    assert lock.plugins[0].version == "2.0.0"
