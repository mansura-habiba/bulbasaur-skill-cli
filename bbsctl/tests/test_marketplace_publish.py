"""bbsctl publish — catalog in-place Claude marketplace contract."""

from __future__ import annotations

import json
from pathlib import Path

from skillctl.cli import main
from skillctl.marketplace.catalog_publish import publish_catalog_artifact


def _seed_catalog_repo(root: Path) -> Path:
    artifact = root / "artifacts" / "devex" / "tools" / "demo-skill"
    src = artifact / "src"
    src.mkdir(parents=True)
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "$schema": "https://code.claude.com/schemas/marketplace.json",
                "name": "catalog",
                "plugins": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (artifact / "manifest.yml").write_text(
        "\n".join(
            [
                "name: demo-skill",
                "title: Demo Skill",
                "type: skill",
                "version: 1.2.3",
                "status: active",
                "home_squad: devex",
                "team: tools",
                "level: team",
                "hosting: local",
                "owners:",
                "  - '@alice'",
                "tags:",
                "  - capability:demo",
                "  - lifecycle:active",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact / "README.md").write_text(
        "# Demo Skill\n\nA short description of the demo skill for marketplace publish.\n",
        encoding="utf-8",
    )
    (src / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo skill for marketplace publish tests.\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    return artifact


def test_publish_catalog_artifact_upserts_claude_and_sidecar(tmp_path: Path):
    artifact = _seed_catalog_repo(tmp_path)
    result = publish_catalog_artifact(artifact, repo_root=tmp_path)
    assert result["name"] == "demo-skill"
    assert result["source"] == "./artifacts/devex/tools/demo-skill/src"
    assert result["marketplace_name"] == "catalog"

    claude = json.loads(
        (tmp_path / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert len(claude["plugins"]) == 1
    assert claude["plugins"][0]["name"] == "demo-skill"
    meta = claude["plugins"][0]["metadata"]
    assert "squad" in meta
    assert "oicSquad" not in meta


def test_publish_via_cli_inplace(tmp_path: Path):
    artifact = _seed_catalog_repo(tmp_path)
    code = main(
        [
            "publish",
            str(artifact),
            "--repo-root",
            str(tmp_path),
            "--inplace",
        ]
    )
    assert code == 0
    claude = json.loads(
        (tmp_path / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert claude["plugins"][0]["name"] == "demo-skill"


def test_publish_inplace_dry_run(tmp_path: Path):
    artifact = _seed_catalog_repo(tmp_path)
    code = main(
        [
            "publish",
            str(artifact),
            "--repo-root",
            str(tmp_path),
            "--inplace",
            "--dry-run",
        ]
    )
    assert code == 0
    assert not (artifact / "marketplace-entry.json").exists()
