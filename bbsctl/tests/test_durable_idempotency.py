"""Idempotency / durable-write contracts for mutate paths."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from skillctl.durable import (
    atomic_write_json,
    atomic_write_text,
    file_lock,
    replace_directory,
)
from skillctl.marketplace.ard import skill_to_ard_entry, write_ard_manifest
from skillctl.marketplace.catalog_publish import (
    publish_catalog_artifact,
    upsert_plugin_entry,
)
from skillctl.marketplace.git_marketplace import GitMarketplace


def test_atomic_write_skips_unchanged(tmp_path: Path):
    path = tmp_path / "x.json"
    assert atomic_write_json(path, {"a": 1}) is True
    mtime = path.stat().st_mtime_ns
    assert atomic_write_json(path, {"a": 1}) is False
    assert path.stat().st_mtime_ns == mtime


def test_atomic_write_text_replaces(tmp_path: Path):
    path = tmp_path / "f.txt"
    atomic_write_text(path, "one\n")
    atomic_write_text(path, "two\n")
    assert path.read_text(encoding="utf-8") == "two\n"


def test_replace_directory_keeps_destination_on_failure(tmp_path: Path):
    dest = tmp_path / "live"
    dest.mkdir()
    (dest / "keep.txt").write_text("safe", encoding="utf-8")
    staging = tmp_path / "stage"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")
    replace_directory(staging, dest)
    assert (dest / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (dest / "keep.txt").exists()


def test_catalog_publish_double_run_converges(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "s" / "t" / "demo"
    src = artifact / "src"
    src.mkdir(parents=True)
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "catalog", "plugins": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    (artifact / "manifest.yml").write_text(
        "name: demo\ntitle: Demo\ntype: skill\nversion: 1.0.0\n"
        "status: active\nhome_squad: s\nteam: t\nlevel: team\n",
        encoding="utf-8",
    )
    (src / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill for idempotent publish.\n---\n",
        encoding="utf-8",
    )
    publish_catalog_artifact(artifact, repo_root=tmp_path)
    claude_1 = (tmp_path / ".claude-plugin" / "marketplace.json").read_text(
        encoding="utf-8"
    )
    side_1 = (artifact / "marketplace-entry.json").read_text(encoding="utf-8")
    publish_catalog_artifact(artifact, repo_root=tmp_path)
    assert (tmp_path / ".claude-plugin" / "marketplace.json").read_text(
        encoding="utf-8"
    ) == claude_1
    assert (artifact / "marketplace-entry.json").read_text(encoding="utf-8") == side_1
    plugins = json.loads(claude_1)["plugins"]
    assert len(plugins) == 1


def test_team_marketplace_publish_double_run(tmp_path: Path):
    mp = GitMarketplace.init(tmp_path / "mp", name="team")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: skill\ndescription: A skill for marketplace publish.\n---\n# S\n",
        encoding="utf-8",
    )
    first = mp.publish_plugin(
        plugin_name="skill-plugin",
        skill_name="skill",
        skill_dir=skill,
    )
    second = mp.publish_plugin(
        plugin_name="skill-plugin",
        skill_name="skill",
        skill_dir=skill,
    )
    assert first == second
    assert len(mp.list_plugins()) == 1
    assert (first / "skills" / "skill" / "SKILL.md").is_file()


def test_ard_upsert_double_run(tmp_path: Path):
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: Skill for ard.\n---\n", encoding="utf-8"
    )
    out = tmp_path / "ard.json"
    entry = skill_to_ard_entry(skill, domain="example.com")
    write_ard_manifest([entry], out)
    body = out.read_text(encoding="utf-8")
    write_ard_manifest([entry], out)
    assert out.read_text(encoding="utf-8") == body


def test_file_lock_serializes_rmw(tmp_path: Path):
    path = tmp_path / "counter.json"
    atomic_write_json(path, {"n": 0})

    def bump(_: int) -> None:
        with file_lock(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["n"] = int(data["n"]) + 1
            atomic_write_json(path, data)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(bump, range(40)))
    assert json.loads(path.read_text(encoding="utf-8"))["n"] == 40


def test_concurrent_catalog_upserts_keep_all_plugins(tmp_path: Path):
    mp = tmp_path / "marketplace.json"
    atomic_write_json(mp, {"name": "catalog", "plugins": []})

    def upsert(i: int) -> None:
        upsert_plugin_entry(
            mp,
            {
                "name": f"plugin-{i}",
                "source": f"./artifacts/p{i}/src",
                "description": f"Plugin {i}",
                "version": "0.1.0",
            },
            marketplace_name="catalog",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(upsert, range(20)))
    plugins = json.loads(mp.read_text(encoding="utf-8"))["plugins"]
    names = {p["name"] for p in plugins}
    assert names == {f"plugin-{i}" for i in range(20)}


def test_concurrent_team_marketplace_publish(tmp_path: Path):
    mp = GitMarketplace.init(tmp_path / "mp", name="team")

    def publish_one(i: int) -> None:
        skill = tmp_path / f"skill-{i}"
        skill.mkdir(exist_ok=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: skill-{i}\ndescription: Skill number {i} for concurrent publish.\n---\n",
            encoding="utf-8",
        )
        mp.publish_plugin(
            plugin_name=f"skill-{i}-plugin",
            skill_name=f"skill-{i}",
            skill_dir=skill,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(publish_one, range(8)))
    names = {p.name for p in mp.list_plugins()}
    assert names == {f"skill-{i}-plugin" for i in range(8)}
