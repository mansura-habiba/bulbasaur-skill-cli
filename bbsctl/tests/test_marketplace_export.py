"""Tests for `bbsctl marketplace export` — bulk OIC catalog conversion.

Covers:
  - dry-run reports correct counts without writing files
  - live export publishes skill/mcp-server assets and skips library/unsupported/deprecated
  - CLI integration via skillctl.cli:main
  - `bbsctl publish --marketplace` uses manifest.yml fields when present
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillctl.cli import main
from skillctl.marketplace.git_marketplace import GitMarketplace


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_SKILL_MANIFEST = (
    "name: {name}\n"
    "title: {title}\n"
    "type: skill\n"
    "level: team\n"
    "status: active\n"
    "version: 1.0.0\n"
    "owners:\n"
    "  - \"@test-owner\"\n"
)

_VALID_MCP_MANIFEST = (
    "name: {name}\n"
    "title: {title}\n"
    "type: mcp-server\n"
    "level: team\n"
    "status: active\n"
    "version: 1.0.0\n"
    "owners:\n"
    "  - \"@test-owner\"\n"
)

_LIBRARY_MANIFEST = (
    "name: bbsctl-lib\n"
    "title: Bulbasaur Library\n"
    "type: library\n"
    "level: team\n"
    "status: active\n"
    "version: 0.1.0\n"
    "owners:\n"
    "  - \"@test-owner\"\n"
)

_DEPRECATED_MANIFEST = (
    "name: old-skill\n"
    "title: Old Skill\n"
    "type: skill\n"
    "level: team\n"
    "status: deprecated\n"
    "version: 1.0.0\n"
    "owners:\n"
    "  - \"@test-owner\"\n"
)


def _make_catalog(tmp_path: Path) -> Path:
    """Build a small OIC-style catalog with mixed artifact types."""
    catalog = tmp_path / "artifacts"
    # publishable skill
    skill_dir = catalog / "mcsp" / "sre" / "cluster-debug"
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.yml").write_text(
        _VALID_SKILL_MANIFEST.format(name="cluster-debug", title="Cluster Debug"),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: cluster-debug\ndescription: Debugging skill.\n---\nBody.\n",
        encoding="utf-8",
    )

    # publishable mcp-server
    mcp_dir = catalog / "mcsp" / "sre" / "my-mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "manifest.yml").write_text(
        _VALID_MCP_MANIFEST.format(name="my-mcp", title="My MCP Server"),
        encoding="utf-8",
    )

    # library — must be skipped
    lib_dir = catalog / "devex" / "bbsctl"
    lib_dir.mkdir(parents=True)
    (lib_dir / "manifest.yml").write_text(_LIBRARY_MANIFEST, encoding="utf-8")

    # deprecated — must be skipped
    dep_dir = catalog / "devex" / "old-skill"
    dep_dir.mkdir(parents=True)
    (dep_dir / "manifest.yml").write_text(_DEPRECATED_MANIFEST, encoding="utf-8")

    return catalog


# ── Unit: _run_export ─────────────────────────────────────────────────────────

def test_export_dry_run_reports_counts(tmp_path: Path, capsys) -> None:
    catalog = _make_catalog(tmp_path)
    mp_dir = tmp_path / "marketplace"
    GitMarketplace.init(mp_dir, name="test-mp")

    rc = main([
        "marketplace", "export",
        "--catalog", str(catalog),
        "--marketplace", str(mp_dir),
        "--dry-run",
    ])
    assert rc == 0

    out = capsys.readouterr().out
    assert "published : 2" in out
    assert "skipped   : 2" in out
    assert "failed    : 0" in out

    # Dry-run must NOT write any plugin directories
    plugins_dir = mp_dir / "plugins"
    assert list(plugins_dir.iterdir()) == [plugins_dir / ".gitkeep"]


def test_export_live_publishes_and_skips(tmp_path: Path, capsys) -> None:
    catalog = _make_catalog(tmp_path)
    mp_dir = tmp_path / "marketplace"
    mp = GitMarketplace.init(mp_dir, name="test-mp")

    rc = main([
        "marketplace", "export",
        "--catalog", str(catalog),
        "--marketplace", str(mp_dir),
    ])
    assert rc == 0

    plugins = mp.list_plugins()
    plugin_names = {p.name for p in plugins}
    assert "cluster-debug-plugin" in plugin_names
    assert "my-mcp-plugin" in plugin_names
    assert len(plugins) == 2  # library and deprecated must not appear

    out = capsys.readouterr().out
    assert "published : 2" in out
    assert "skipped   : 2" in out


def test_export_missing_catalog_returns_1(tmp_path: Path) -> None:
    mp_dir = tmp_path / "marketplace"
    GitMarketplace.init(mp_dir, name="test-mp")

    rc = main([
        "marketplace", "export",
        "--catalog", str(tmp_path / "does-not-exist"),
        "--marketplace", str(mp_dir),
    ])
    assert rc == 1


def test_export_missing_marketplace_returns_1(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path)

    rc = main([
        "marketplace", "export",
        "--catalog", str(catalog),
        "--marketplace", str(tmp_path / "no-marketplace"),
    ])
    assert rc == 1


def test_export_no_manifests_returns_0(tmp_path: Path, capsys) -> None:
    empty_catalog = tmp_path / "empty"
    empty_catalog.mkdir()
    mp_dir = tmp_path / "marketplace"
    GitMarketplace.init(mp_dir, name="test-mp")

    rc = main([
        "marketplace", "export",
        "--catalog", str(empty_catalog),
        "--marketplace", str(mp_dir),
    ])
    assert rc == 0


# ── CLI: bbsctl publish --marketplace with manifest.yml present ───────────────

def test_publish_with_manifest_uses_manifest_fields(tmp_path: Path, capsys) -> None:
    """publish --marketplace should derive name/description from manifest.yml."""
    skill_dir = tmp_path / "cluster-debug"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: cluster-debug\ndescription: Debugging skill from SKILL.md.\n---\nBody.\n",
        encoding="utf-8",
    )
    # manifest title should win over SKILL.md description
    (skill_dir / "manifest.yml").write_text(
        "name: cluster-debug\n"
        "title: Cluster Debug (from manifest)\n"
        "type: skill\n"
        "level: team\n"
        "status: active\n"
        "version: 2.0.0\n"
        "owners:\n"
        "  - \"@test-owner\"\n",
        encoding="utf-8",
    )

    mp_dir = tmp_path / "mp"
    GitMarketplace.init(mp_dir, name="test-mp")

    rc = main(["publish", str(skill_dir), "--marketplace", str(mp_dir)])
    assert rc == 0

    mp = GitMarketplace(mp_dir)
    plugins = mp.list_plugins()
    assert len(plugins) == 1
    assert plugins[0].name == "cluster-debug-plugin"
    assert plugins[0].description == "Cluster Debug (from manifest)"

    plugin_json_path = mp_dir / "plugins" / "cluster-debug-plugin" / ".claude-plugin" / "plugin.json"
    assert plugin_json_path.exists()
    pdata = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    assert pdata["version"] == "2.0.0"
    assert pdata["author"]["name"] == "test-owner"
