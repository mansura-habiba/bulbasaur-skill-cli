"""Behavioral evaluator admission, real runner invocation and API contract tests."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from bulbasaur_api.app import create_app
from bulbasaur_api.behavior import EvaluationConfigurationError, load_operator_policy, normalize_request
from bulbasaur_api.service import SkillAssessmentService

ROOT = Path(__file__).resolve().parents[1]
SKILL = """---
name: reply-helper
description: Respond with a fixed greeting when asked.
---

## Instructions
Reply with: "Hello there"
"""
CASES = [{"id": "greeting-1", "prompt": "Greet the user",
          "expected_output": "Hello there", "assertions": ["Hello there"]}]
REQUEST = {"enabled": True, "runtime": "mock", "judge": "heuristic",
           "threshold": 1.0, "cases": CASES}


def test_default_keeps_not_run_v1() -> None:
    result = SkillAssessmentService().assess("reply-helper", SKILL)
    assert result["schema_version"] == "bulbasaur.assessment/v1"
    assert result["behavioral_evaluation"] == "not_run"


def test_opt_in_executes_real_existing_eval_runner() -> None:
    result = SkillAssessmentService().assess("reply-helper", SKILL, evaluation=REQUEST)
    assert result["schema_version"] == "bulbasaur.assessment/v2"
    evidence = result["behavioral_evaluation"]
    assert evidence["status"] == "passed"
    assert evidence["mode"] == "deterministic_mock"
    assert evidence["cases_run"] == 1
    assert evidence["cases_passed"] == 1
    assert evidence["score"] == 1.0
    assert len(evidence["corpus_sha256"]) == 64
    schema = json.loads((ROOT / "contracts/assessment.v2.schema.json").read_text())
    Draft202012Validator(schema).validate(result)


def test_failing_eval_is_not_reported_as_passed() -> None:
    requested = {**REQUEST, "cases": [{
        "id": "wrong", "prompt": "Greet", "assertions": ["Goodbye moon"],
    }]}
    result = SkillAssessmentService().assess("reply-helper", SKILL, evaluation=requested)
    assert result["status"] == "failed"
    assert result["behavioral_evaluation"]["cases_passed"] == 0


def test_empty_cases_and_unapproved_runtime_refused() -> None:
    service = SkillAssessmentService()
    for cfg in ({**REQUEST, "cases": []}, {**REQUEST, "runtime": "ollama"},
                {**REQUEST, "runtime": "pi"},
                {**REQUEST, "judge": "llm"}):
        result = service.assess("reply-helper", SKILL, evaluation=cfg)
        assert result["status"] == "failed"
        assert result["behavioral_evaluation"] == "not_run"
        assert result["findings"][0]["code"] == "evaluation_configuration"


def test_operator_config_and_invalid_config(monkeypatch, tmp_path) -> None:
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"allowed_runtimes": ["mock"], "max_cases": 1,
                                  "enable_real_runtimes": False}))
    monkeypatch.setenv("BULBASAUR_EVAL_CONFIG", str(config))
    assert load_operator_policy().max_cases == 1
    assert SkillAssessmentService().assess(
        "reply-helper", SKILL, evaluation=REQUEST
    )["behavioral_evaluation"]["status"] == "passed"
    config.write_text(json.dumps({"allowed_runtimes": ["ollama"],
                                  "enable_real_runtimes": False}))
    with pytest.raises(EvaluationConfigurationError):
        load_operator_policy()


def test_rest_input_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("BULBASAUR_HTTP_TOKEN", "test-only-secret")
    with TestClient(create_app().http_app()) as client:
        response = client.post("/v1/skills/assess", json={
            "skill_name": "reply-helper", "skill_md": SKILL, "evaluation": REQUEST,
        }, headers={"Authorization": "Bearer test-only-secret"})
        assert response.status_code == 200
        assert response.json()["behavioral_evaluation"]["cases_run"] == 1


def test_example_request() -> None:
    request = json.loads((ROOT / "examples/behavioral-evaluation/request.json").read_text())
    result = SkillAssessmentService().assess(
        request["skill_name"], request["skill_md"],
        profile=request["profile"], evaluation=request["evaluation"])
    assert result["behavioral_evaluation"]["cases_run"] == 1
