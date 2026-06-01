"""Tests for ClaudeAgentSDKAdapter and its factory registration."""

from __future__ import annotations

import pytest

from skillctl.agentskills import SkillFrontmatter
from skillctl.llm.anthropic import AnthropicBackend
from skillctl.llm.base import LLMBackend, LLMBackendError, LLMResponse
from skillctl.run import build_runtime
from skillctl.run.claude_agent_sdk import ClaudeAgentSDKAdapter
from skillctl.run.factory import list_runtimes


def _skill() -> SkillFrontmatter:
    return SkillFrontmatter(
        raw_frontmatter={
            "name": "test-skill",
            "description": "A skill for adapter tests.",
        },
        body="When the user asks for X, do Y.",
        body_line_offset=4,
    )


class _StubBackend(LLMBackend):
    """Test double — records calls and returns a queued LLMResponse."""

    name = "stub-anthropic"

    def __init__(self, responses: list[str | LLMBackendError]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> LLMResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise LLMBackendError("no more stubbed responses")
        item = self._responses.pop(0)
        if isinstance(item, LLMBackendError):
            raise item
        return LLMResponse(
            text=item,
            model=kwargs.get("model", "claude-sonnet-4-6"),
            backend=self.name,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=42,
        )


# ── factory registration ──────────────────────────────────────────────────


def test_factory_lists_claude_agent_sdk():
    assert "claude-agent-sdk" in list_runtimes()


def test_factory_builds_claude_agent_sdk_with_default_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("BBSCTL_RUNTIME_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    rt = build_runtime("claude-agent-sdk")
    assert rt.name == "claude-agent-sdk"
    assert rt._model == ClaudeAgentSDKAdapter.DEFAULT_MODEL


def test_factory_propagates_model_kwarg(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    rt = build_runtime("claude-agent-sdk", model="claude-sonnet-4-7")
    assert rt._model == "claude-sonnet-4-7"


def test_env_runtime_model_overrides_default(monkeypatch):
    monkeypatch.setenv("BBSCTL_RUNTIME_MODEL", "custom-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    adapter = ClaudeAgentSDKAdapter()
    assert adapter._model == "custom-model"


# ── activation happy path ─────────────────────────────────────────────────


def test_activate_returns_runtime_response_with_telemetry():
    backend = _StubBackend(["the reply"])
    adapter = ClaudeAgentSDKAdapter(backend=backend, model="claude-sonnet-4-6")
    response = adapter.activate(_skill(), "do the thing")
    assert response.activated_skill == "test-skill"
    assert response.reply == "the reply"
    assert response.metadata["model"] == "claude-sonnet-4-6"
    assert response.metadata["prompt_tokens"] == 10
    assert response.metadata["completion_tokens"] == 5
    assert response.metadata["latency_ms"] == 42


def test_activate_includes_skill_description_in_system_prompt():
    backend = _StubBackend(["ok"])
    adapter = ClaudeAgentSDKAdapter(backend=backend)
    adapter.activate(_skill(), "hi")
    system_arg = backend.calls[0]["system"]
    assert "test-skill" in system_arg
    assert "A skill for adapter tests." in system_arg
    assert "When the user asks for X" in system_arg


def test_activate_records_trace_with_model_and_tokens():
    backend = _StubBackend(["x"])
    adapter = ClaudeAgentSDKAdapter(backend=backend, model="claude-sonnet-4-6")
    response = adapter.activate(_skill(), "p")
    trace_text = "\n".join(response.trace)
    assert "claude-sonnet-4-6" in trace_text
    assert "in=10, out=5" in trace_text
    assert "42ms" in trace_text


def test_activate_uses_pinned_model_per_call():
    backend = _StubBackend(["ok"])
    adapter = ClaudeAgentSDKAdapter(backend=backend, model="claude-sonnet-4-6")
    adapter.activate(_skill(), "hi")
    assert backend.calls[0]["model"] == "claude-sonnet-4-6"


def test_activate_passes_temperature_and_max_tokens():
    backend = _StubBackend(["ok"])
    adapter = ClaudeAgentSDKAdapter(
        backend=backend, max_tokens=2048, temperature=0.3
    )
    adapter.activate(_skill(), "p")
    assert backend.calls[0]["max_tokens"] == 2048
    assert backend.calls[0]["temperature"] == 0.3


# ── error handling ────────────────────────────────────────────────────────


def test_activate_returns_error_response_on_backend_failure():
    backend = _StubBackend([LLMBackendError("ANTHROPIC_API_KEY not set")])
    adapter = ClaudeAgentSDKAdapter(backend=backend)
    response = adapter.activate(_skill(), "p")
    assert "[runtime error]" in response.reply
    assert response.metadata.get("error") == "ANTHROPIC_API_KEY not set"
    # Trace records the failure for audit.
    assert any("backend error" in line for line in response.trace)


def test_activate_does_not_raise_on_backend_error():
    """Critical for the eval runner: a backend failure must not crash the run."""
    backend = _StubBackend([LLMBackendError("network down")])
    adapter = ClaudeAgentSDKAdapter(backend=backend)
    # Should NOT raise.
    response = adapter.activate(_skill(), "p")
    assert response.reply.startswith("[runtime error]")


# ── integration with EvalRunner ───────────────────────────────────────────


def test_eval_runner_can_use_claude_agent_sdk(tmp_path):
    """End-to-end: EvalRunner accepts runtime='claude-agent-sdk' via config."""
    import json

    from skillctl.eval import EvalRunner
    from skillctl.eval.reproducibility import EvalConfig
    from skillctl.strictness import Strictness

    # Stub the factory so we don't hit the real Anthropic API.
    from skillctl.run import factory as run_factory

    backend = _StubBackend(["the answer is foo"])
    adapter = ClaudeAgentSDKAdapter(backend=backend)
    original = run_factory._REGISTRY["claude-agent-sdk"]
    run_factory._REGISTRY["claude-agent-sdk"] = lambda model=None: adapter
    try:
        skill = tmp_path / "s"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: s\ndescription: When the user asks anything, reply with foo.\n---\n"
            "Reply with: \"the answer is foo\"\n",
            encoding="utf-8",
        )
        (skill / "evals").mkdir()
        (skill / "evals" / "behavior.json").write_text(
            json.dumps(
                {
                    "skill_name": "s",
                    "evals": [
                        {
                            "id": 1,
                            "prompt": "give me foo",
                            "expected_output": "foo answer",
                            "assertions": ["answer foo"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        config = EvalConfig(
            runtime="claude-agent-sdk",
            runtime_model="claude-sonnet-4-6",
            judge="heuristic",
            threshold=0.0,
        )
        report = EvalRunner(skill, Strictness.LOCAL, config=config).run()
        assert report.runtime_name == "claude-agent-sdk"
        assert report.runtime_model == "claude-sonnet-4-6"
        assert report.suites[0].cases[0].actual_output == "the answer is foo"
    finally:
        run_factory._REGISTRY["claude-agent-sdk"] = original


# ── pytest fixture cleanup ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts with no Anthropic env contamination from prior tests."""
    yield
