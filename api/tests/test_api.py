"""Contract tests covering REST, MCP, reusable assessment and schema fixtures."""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from fastmcp import Client
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from bulbasaur_api.app import assess_skill, create_app, validate_skill
from bulbasaur_api.service import SkillAssessmentService

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
VALID = """---
name: log-analyzer
description: Analyze application logs and identify common errors.
---

## Instructions
Read logs and report failures without changing the original data.
"""


def test_reusable_library_and_result_contract() -> None:
    service = SkillAssessmentService()
    report = service.assess("log-analyzer", VALID)
    assert report["status"] == "passed"
    assert report["behavioral_evaluation"] == "not_run"
    assert report["catalog_approval"] == "not_applicable"
    assert report["assessment"]["checks_run"] >= 2
    schema = json.loads((CONTRACTS / "assessment.v1.schema.json").read_text())
    Draft202012Validator(schema).validate(report)


def test_legacy_validation_and_failing_skill() -> None:
    assert validate_skill("log-analyzer", VALID)["artifact_sha256"] == hashlib.sha256(VALID.encode()).hexdigest()
    assert validate_skill("log-analyzer", "not frontmatter")["status"] == "failed"
    failed = assess_skill("log-analyzer", "not frontmatter")
    assert failed["status"] == "failed"
    assert failed["findings"]
    assert failed["behavioral_evaluation"] == "not_run"


def test_invalid_profile_and_size() -> None:
    assert assess_skill("log-analyzer", VALID, "invalid")["status"] == "failed"
    assert assess_skill("../escape", VALID)["status"] == "failed"
    assert validate_skill("log-analyzer", "x" * (128 * 1024 + 1))["status"] == "failed"


def test_rest_auth_validate_and_assess(monkeypatch) -> None:
    monkeypatch.setenv("BULBASAUR_HTTP_TOKEN", "test-only-secret")
    with TestClient(create_app().http_app()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        payload = {"skill_name": "log-analyzer", "skill_md": VALID}
        assert client.post("/v1/skills/assess", json=payload).status_code == 401
        for route in ("/v1/skills/validate", "/v1/skills/assess"):
            response = client.post(route, json=payload, headers={
                "Authorization": "Bearer test-only-secret"
            })
            assert response.status_code == 200
            assert response.json()["status"] == "passed"


def test_rest_body_limit(monkeypatch) -> None:
    monkeypatch.setenv("BULBASAUR_HTTP_TOKEN", "test-only-secret")
    with TestClient(create_app().http_app()) as client:
        result = client.post("/v1/skills/assess", content=b"x" * (128 * 1024 + 5000),
                             headers={"Authorization": "Bearer test-only-secret"})
        assert result.status_code == 413


def test_mcp_tools_registered_and_callable() -> None:
    async def check() -> None:
        async with Client(create_app()) as client:
            names = {t.name for t in await client.list_tools()}
            assert {"validate_agent_skill", "assess_agent_skill"} <= names
            for name in ("validate_agent_skill", "assess_agent_skill"):
                result = await client.call_tool(name, {
                    "skill_name": "log-analyzer", "skill_md": VALID
                })
                assert not result.is_error
    asyncio.run(check())


@pytest.mark.parametrize("kind", ["eval", "control"])
def test_custom_resource_descriptor_examples(kind: str) -> None:
    schema = json.loads((CONTRACTS / f"{kind}-resource.v1.schema.json").read_text())
    example = json.loads((CONTRACTS / "examples" / (
        "skill-injection-eval.json" if kind == "eval" else "skill-guardrail-control.json"
    )).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(example)
    invalid = dict(example)
    invalid["unexpected"] = "not allowed"
    assert list(Draft202012Validator(schema).iter_errors(invalid))


def test_catalog_lifecycle_remains_separate() -> None:
    report = assess_skill("log-analyzer", VALID)
    assert "catalog_release" not in report
    assert "catalog_resource_id" not in report
    assert report["catalog_approval"] == "not_applicable"
