"""Tests for the LLM backend adapter and LLMJudge.

Mocks urllib so tests do not hit real APIs. Verifies adapter shape, error
handling, and JSON-parsing recovery in the judge.
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from skillctl.llm import LLMBackendError, build_backend, list_backends
from skillctl.llm.anthropic import AnthropicBackend
from skillctl.llm.ollama import OllamaBackend
from skillctl.llm.openai import OpenAIBackend


# ── factory ────────────────────────────────────────────────────────────────


def test_list_backends_returns_all_three():
    assert set(list_backends()) >= {"ollama", "anthropic", "openai"}


def test_build_backend_default_is_ollama(monkeypatch):
    monkeypatch.delenv("BBSCTL_LLM_BACKEND", raising=False)
    b = build_backend()
    assert b.name == "ollama"


def test_build_backend_respects_env(monkeypatch):
    monkeypatch.setenv("BBSCTL_LLM_BACKEND", "openai")
    b = build_backend()
    assert b.name == "openai"


def test_build_backend_argument_overrides_env(monkeypatch):
    monkeypatch.setenv("BBSCTL_LLM_BACKEND", "openai")
    b = build_backend("ollama")
    assert b.name == "ollama"


def test_build_backend_unknown_name_raises():
    with pytest.raises(ValueError, match="unknown LLM backend"):
        build_backend("not-a-real-backend")


# ── helpers ────────────────────────────────────────────────────────────────


def _mock_urlopen(payload: dict, **kwargs):
    """Return a context manager that yields a response object reading payload."""

    class _Resp:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _Resp(json.dumps(payload).encode("utf-8"))


# ── OllamaBackend ──────────────────────────────────────────────────────────


def test_ollama_backend_happy_path():
    backend = OllamaBackend(host="http://test:11434", default_model="llama3:8b")
    payload = {
        "model": "llama3:8b",
        "response": "hello world",
        "prompt_eval_count": 12,
        "eval_count": 4,
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        resp = backend.complete(prompt="hi")
    assert resp.text == "hello world"
    assert resp.model == "llama3:8b"
    assert resp.backend == "ollama"
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 4


def test_ollama_backend_raises_on_unreachable():
    backend = OllamaBackend(host="http://nope:11434")
    with patch("urllib.request.urlopen", side_effect=URLError("connection refused")):
        with pytest.raises(LLMBackendError, match="Ollama unreachable"):
            backend.complete(prompt="hi")


def test_ollama_backend_uses_env_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:14b")
    backend = OllamaBackend()
    assert backend._default_model == "qwen2.5:14b"


# ── AnthropicBackend ───────────────────────────────────────────────────────


def test_anthropic_backend_missing_key_raises_at_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    backend = AnthropicBackend()
    with pytest.raises(LLMBackendError, match="ANTHROPIC_API_KEY"):
        backend.complete(prompt="hi")


def test_anthropic_backend_happy_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    backend = AnthropicBackend()
    payload = {
        "id": "msg_123",
        "model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": "hi there"}],
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        resp = backend.complete(prompt="hi", system="be brief")
    assert resp.text == "hi there"
    assert resp.backend == "anthropic"
    assert resp.prompt_tokens == 5
    assert resp.completion_tokens == 2


def test_anthropic_backend_handles_http_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    backend = AnthropicBackend()
    fp = BytesIO(b'{"error":"rate_limited"}')
    http_err = HTTPError(
        AnthropicBackend.API_URL, 429, "Too Many Requests", {}, fp
    )
    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(LLMBackendError, match="Anthropic API error 429"):
            backend.complete(prompt="hi")


# ── OpenAIBackend ──────────────────────────────────────────────────────────


def test_openai_backend_happy_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    backend = OpenAIBackend()
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        resp = backend.complete(prompt="hi", system="be brief")
    assert resp.text == "ok"
    assert resp.backend == "openai"


def test_openai_backend_supports_custom_api_base(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_BASE", "http://localhost:1234/v1")
    backend = OpenAIBackend()
    assert backend._api_base == "http://localhost:1234/v1"


def test_openai_backend_missing_key_raises_at_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend = OpenAIBackend()
    with pytest.raises(LLMBackendError, match="OPENAI_API_KEY"):
        backend.complete(prompt="hi")


# ── LLMJudge ───────────────────────────────────────────────────────────────


from skillctl.eval.llm_judge import LLMJudge  # noqa: E402
from skillctl.llm.base import LLMBackend, LLMResponse  # noqa: E402


class _StubBackend(LLMBackend):
    """Test double: returns the queued responses in order, then raises."""

    name = "stub"

    def __init__(self, responses: list[str | LLMBackendError]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> LLMResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise LLMBackendError("no more stubbed responses")
        resp = self._responses.pop(0)
        if isinstance(resp, LLMBackendError):
            raise resp
        return LLMResponse(
            text=resp, model="stub-model", backend=self.name
        )


def test_llm_judge_parses_clean_json_verdict():
    backend = _StubBackend(['{"passed": true, "reason": "matches"}'])
    judge = LLMJudge(backend=backend)
    v = judge.score(
        assertion="output mentions kubectl",
        actual_output="kubectl rollout restart was executed",
        expected_output="ValidationReport",
    )
    assert v.passed is True
    assert v.reason == "matches"
    assert len(backend.calls) == 1


def test_llm_judge_extracts_json_object_from_prose():
    backend = _StubBackend(
        ['Let me think... {"passed": false, "reason": "missing"} ok']
    )
    judge = LLMJudge(backend=backend)
    v = judge.score(
        assertion="x",
        actual_output="y",
        expected_output="z",
    )
    assert v.passed is False
    assert v.reason == "missing"


def test_llm_judge_retries_on_malformed_json():
    backend = _StubBackend(
        [
            "I don't know how to answer",  # unparseable
            '{"passed": true, "reason": "second try"}',
        ]
    )
    judge = LLMJudge(backend=backend)
    v = judge.score(assertion="x", actual_output="y", expected_output="z")
    assert v.passed is True
    assert v.reason == "second try"
    assert len(backend.calls) == 2


def test_llm_judge_fails_gracefully_when_retry_also_fails():
    backend = _StubBackend(["nope", "still nope"])
    judge = LLMJudge(backend=backend)
    v = judge.score(assertion="x", actual_output="y", expected_output="z")
    assert v.passed is False
    assert "could not parse" in v.reason


def test_llm_judge_returns_failing_verdict_on_backend_error():
    backend = _StubBackend([LLMBackendError("network down")])
    judge = LLMJudge(backend=backend)
    v = judge.score(assertion="x", actual_output="y", expected_output="z")
    assert v.passed is False
    assert "backend error" in v.reason


# ── factory integration ────────────────────────────────────────────────────


def test_eval_factory_lists_llm_judge():
    from skillctl.eval.factory import list_judges

    assert "llm" in list_judges()


def test_eval_factory_build_llm_judge_constructs_lazily(monkeypatch):
    """`build_judge('llm')` should return an LLMJudge backed by the default."""
    from skillctl.eval.factory import build_judge

    monkeypatch.delenv("BBSCTL_LLM_BACKEND", raising=False)
    judge = build_judge("llm")
    assert isinstance(judge, LLMJudge)
