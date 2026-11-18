"""Contract tests covering shared validation, REST route and MCP tool."""
import asyncio
import hashlib

from fastmcp import Client
from starlette.testclient import TestClient

from bulbasaur_api.app import create_app, validate_skill

VALID = """---
name: log-analyzer
description: Analyze application logs and identify common errors.
---

## Instructions
Read logs and report failures without changing the original data.
"""


def test_valid_and_invalid_skill() -> None:
    result = validate_skill("log-analyzer", VALID)
    assert result["status"] == "passed"
    assert result["artifact_sha256"] == hashlib.sha256(VALID.encode()).hexdigest()
    assert validate_skill("log-analyzer", "not frontmatter")["status"] == "failed"


def test_path_and_oversized_skill_rejected() -> None:
    assert validate_skill("../escape", VALID)["status"] == "failed"
    assert validate_skill("log-analyzer", "x" * (128 * 1024 + 1))["findings"][0]["code"] == "size_limit"


def test_rest_auth_and_validation(monkeypatch) -> None:
    monkeypatch.setenv("BULBASAUR_HTTP_TOKEN", "test-only-secret")
    with TestClient(create_app().http_app()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        payload = {"skill_name": "log-analyzer", "skill_md": VALID}
        assert client.post("/v1/skills/validate", json=payload).status_code == 401
        result = client.post("/v1/skills/validate", json=payload, headers={
            "Authorization": "Bearer test-only-secret"
        })
        assert result.status_code == 200
        assert result.json()["status"] == "passed"


def test_rest_body_limit(monkeypatch) -> None:
    monkeypatch.setenv("BULBASAUR_HTTP_TOKEN", "test-only-secret")
    with TestClient(create_app().http_app()) as client:
        result = client.post("/v1/skills/validate", content=b"x" * (128 * 1024 + 5000),
                             headers={"Authorization": "Bearer test-only-secret"})
        assert result.status_code == 413


def test_mcp_tool_registered_and_callable() -> None:
    async def check() -> None:
        async with Client(create_app()) as client:
            tools = await client.list_tools()
            assert "validate_agent_skill" in {t.name for t in tools}
            result = await client.call_tool("validate_agent_skill", {
                "skill_name": "log-analyzer", "skill_md": VALID
            })
            assert not result.is_error
    asyncio.run(check())
