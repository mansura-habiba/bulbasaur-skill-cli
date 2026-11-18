"""HTTP contract smoke tests for the structural validation endpoint."""
import hashlib

from fastapi.testclient import TestClient

from bulbasaur_api.app import create_app

client = TestClient(create_app())

VALID = """---
name: log-analyzer
description: Analyze application logs and identify common errors.
---

## Instructions
Read logs and report failures without changing the original data.
"""


def test_health() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_valid_skill() -> None:
    result = client.post(
        "/v1/skills/validate", json={"skill_name": "log-analyzer", "skill_md": VALID}
    )
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "passed"
    assert body["findings"] == []
    assert body["artifact_sha256"] == hashlib.sha256(VALID.encode()).hexdigest()


def test_invalid_frontmatter_is_not_approved() -> None:
    result = client.post(
        "/v1/skills/validate", json={"skill_name": "log-analyzer", "skill_md": "not frontmatter"}
    )
    assert result.status_code == 200
    assert result.json()["status"] == "failed"
    assert result.json()["findings"][0]["code"] == "invalid_skill"


def test_path_like_skill_name_rejected() -> None:
    result = client.post(
        "/v1/skills/validate", json={"skill_name": "../escape", "skill_md": VALID}
    )
    assert result.status_code == 200
    assert result.json()["findings"][0]["code"] == "invalid_name"


def test_size_limit() -> None:
    value = VALID + ("x" * (128 * 1024))
    result = client.post(
        "/v1/skills/validate", json={"skill_name": "log-analyzer", "skill_md": value}
    )
    assert result.status_code in (200, 422)
    if result.status_code == 200:
        assert result.json()["findings"][0]["code"] == "size_limit"
