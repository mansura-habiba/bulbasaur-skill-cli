"""Tests for the OIC ManifestConverter and plugin commands."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from skillctl.marketplace.converter import (
    ManifestConverter,
    verify_strict_mode_conflict,
    ManifestConverterError,
    CLAUDE_RESERVED_MARKETPLACE_NAMES,
)
from skillctl.marketplace.git_marketplace import GitMarketplace, MarketplaceEntry
from skillctl.messaging import FrameworkError


def test_converter_validation_success(tmp_path: Path) -> None:
    # 1. Create a valid manifest.yml
    skill_dir = tmp_path / "cluster-debug"
    skill_dir.mkdir()
    manifest_yml = skill_dir / "manifest.yml"
    manifest_yml.write_text(
        "name:          cluster-debug\n"
        "title:         Kubernetes Cluster Debugging Skill\n"
        "type:          skill\n"
        "level:         org\n"
        "status:        active\n"
        "version:       1.2.4\n"
        "hosting:       linked\n"
        "source_repo:   \"https://github.com/ibm/mcsp-cluster-debug-mcp\"\n"
        "tags:\n"
        "  - devops\n"
        "  - kubernetes\n"
        "owners:\n"
        "  - \"@m-smith\"\n"
        "  - \"@j-doe\"\n"
        "contributors:\n"
        "  - \"@a-developer\"\n"
        "promotion:\n"
        "  approved:    true\n",
        encoding="utf-8",
    )

    converter = ManifestConverter(skill_dir)
    warnings = converter.validate()
    assert len(warnings) == 0

    # Test convert to plugin.json
    plugin_json = converter.convert_to_plugin_json()
    assert plugin_json["name"] == "cluster-debug-plugin"
    assert plugin_json["version"] == "1.2.4"
    assert plugin_json["description"] == "Kubernetes Cluster Debugging Skill"
    assert plugin_json["author"]["name"] == "m-smith"
    assert plugin_json["author"]["url"] == "https://github.com/ibm/mcsp-cluster-debug-mcp"
    assert plugin_json["keywords"] == ["Devops", "Kubernetes"]
    assert "j-doe" in plugin_json["contributors"]
    assert "a-developer" in plugin_json["contributors"]
    assert plugin_json["skills"] == ["./skills/cluster-debug/SKILL.md"]

    # Test convert to marketplace.json entry
    entry = converter.convert_to_marketplace_entry()
    assert entry["name"] == "cluster-debug-plugin"
    assert entry["displayName"] == "Kubernetes Cluster Debugging Skill"
    assert entry["strict"] is False  # external and org level -> strict: False
    assert entry["category"] == "devops"


def test_converter_validation_errors(tmp_path: Path) -> None:
    skill_dir = tmp_path / "bad-skill"
    skill_dir.mkdir()
    manifest_yml = skill_dir / "manifest.yml"

    # Test missing name
    manifest_yml.write_text("version: 1.0.0\n", encoding="utf-8")
    converter = ManifestConverter(skill_dir)
    with pytest.raises(ManifestConverterError) as exc_info:
        converter.validate()
    assert "missing required field `name`" in str(exc_info.value)

    # Test reserved name
    manifest_yml.write_text("name: healthcare\nversion: 1.0.0\n", encoding="utf-8")
    converter = ManifestConverter(skill_dir)
    with pytest.raises(ManifestConverterError) as exc_info:
        converter.validate()
    assert "reserved for official Anthropic use" in str(exc_info.value)

    # Test bad SemVer
    manifest_yml.write_text("name: my-skill\nversion: bad-version\n", encoding="utf-8")
    converter = ManifestConverter(skill_dir)
    with pytest.raises(ManifestConverterError) as exc_info:
        converter.validate()
    assert "is not SemVer-compliant" in str(exc_info.value)

    # Test deprecated status
    manifest_yml.write_text(
        "name: my-skill\nversion: 1.0.0\nstatus: deprecated\n", encoding="utf-8"
    )
    converter = ManifestConverter(skill_dir)
    with pytest.raises(ManifestConverterError) as exc_info:
        converter.validate()
    assert "asset status is 'deprecated'" in str(exc_info.value)

    # Test org-level missing approval
    manifest_yml.write_text(
        "name: my-skill\nversion: 1.0.0\nlevel: org\nstatus: active\ntype: skill\n",
        encoding="utf-8",
    )
    converter = ManifestConverter(skill_dir)
    with pytest.raises(ManifestConverterError) as exc_info:
        converter.validate()
    assert "governance gate violation" in str(exc_info.value)


def test_strict_mode_derivation(tmp_path: Path) -> None:
    # 1. First-party / internal -> strict: True
    skill_dir_1 = tmp_path / "skill-strict-1"
    skill_dir_1.mkdir()
    manifest_yml_1 = skill_dir_1 / "manifest.yml"
    manifest_yml_1.write_text(
        "name: skill-strict-1\nversion: 1.0.0\nlevel: team\nhosting: local\nstatus: active\ntype: skill\n",
        encoding="utf-8",
    )
    converter1 = ManifestConverter(skill_dir_1)
    assert converter1.derive_strict_mode() is True

    # 2. External org-curated -> strict: False
    skill_dir_2 = tmp_path / "skill-strict-2"
    skill_dir_2.mkdir()
    manifest_yml_2 = skill_dir_2 / "manifest.yml"
    manifest_yml_2.write_text(
        "name: skill-strict-2\nversion: 1.0.0\nlevel: org\nhosting: linked\nsource_repo: 'https://github.com/some/repo'\nstatus: active\ntype: skill\n",
        encoding="utf-8",
    )
    converter2 = ManifestConverter(skill_dir_2)
    assert converter2.derive_strict_mode() is False


def test_strict_mode_conflict_checker(tmp_path: Path) -> None:
    # Under strict=True, no checks are performed.
    verify_strict_mode_conflict(tmp_path, strict=True)

    # Under strict=False, if no plugin.json exists, OK.
    verify_strict_mode_conflict(tmp_path, strict=False)

    # If plugin.json exists with NO component fields, OK.
    meta_dir = tmp_path / ".claude-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    plugin_json = meta_dir / "plugin.json"
    plugin_json.write_text(json.dumps({"name": "my-plugin"}), encoding="utf-8")
    verify_strict_mode_conflict(tmp_path, strict=False)

    # If plugin.json contains component fields, raises ManifestConverterError
    plugin_json.write_text(json.dumps({"skills": ["./SKILL.md"]}), encoding="utf-8")
    with pytest.raises(ManifestConverterError) as exc_info:
        verify_strict_mode_conflict(tmp_path, strict=False)
    assert "strict mode conflict detected" in str(exc_info.value)


def test_path_substitution(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill-paths"
    skill_dir.mkdir()
    manifest_yml = skill_dir / "manifest.yml"

    # 1. Test hooks substitution
    manifest_yml.write_text(
        "name: skill-paths\nversion: 1.0.0\ntype: skill\nhooks:\n  post_tool_use: true\n",
        encoding="utf-8",
    )
    converter = ManifestConverter(skill_dir)
    plugin_json = converter.convert_to_plugin_json()
    assert "hooks" in plugin_json
    assert plugin_json["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh"

    # 2. Test mcpServer command substitution
    manifest_yml.write_text(
        "name: skill-paths\nversion: 1.0.0\ntype: mcp-server\n",
        encoding="utf-8",
    )
    converter = ManifestConverter(skill_dir)
    plugin_json = converter.convert_to_plugin_json()
    assert "mcpServers" in plugin_json
    assert plugin_json["mcpServers"]["skill_paths"]["command"] == "${CLAUDE_PLUGIN_ROOT}/bin/server"
    assert plugin_json["mcpServers"]["skill_paths"]["args"] == ["--config", "${CLAUDE_PLUGIN_ROOT}/config.json"]


def test_marketplace_compilation_with_manifest(tmp_path: Path) -> None:
    # Scaffold a marketplace
    mp_dir = tmp_path / "marketplace"
    mp = GitMarketplace.init(mp_dir, name="ibm-marketplace")

    # Create skill with manifest.yml
    skill_dir = tmp_path / "cluster-debug"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# SKILL.md", encoding="utf-8")
    (skill_dir / "manifest.yml").write_text(
        "name:          cluster-debug\n"
        "title:         Kubernetes Cluster Debugging Skill\n"
        "type:          skill\n"
        "level:         team\n"
        "status:        active\n"
        "version:       1.2.4\n"
        "owners:\n"
        "  - \"@m-smith\"\n",
        encoding="utf-8",
    )

    # Publish
    plugin_dir = mp.publish_plugin(
        plugin_name="cluster-debug-plugin",
        skill_name="cluster-debug",
        skill_dir=skill_dir,
    )

    assert plugin_dir.exists()
    assert (plugin_dir / ".claude-plugin" / "plugin.json").exists()

    # Read generated plugin.json
    p_data = json.loads((plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert p_data["name"] == "cluster-debug-plugin"
    assert p_data["version"] == "1.2.4"
    assert p_data["author"]["name"] == "m-smith"

    # Read marketplace manifest
    manifest = mp.load_manifest()
    assert manifest.plugin_root == "./plugins"
    assert len(manifest.plugins) == 1
    p_entry = manifest.plugins[0]
    assert p_entry.name == "cluster-debug-plugin"
    assert p_entry.display_name == "Kubernetes Cluster Debugging Skill"
    assert p_entry.strict is True
