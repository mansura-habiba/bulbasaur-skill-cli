"""ClaudeAgentSDKAdapter — real agent runtime backed by Claude.

Implements the `AgentRuntime` interface against the Anthropic Messages API.
Activates a skill by sending the skill body as a system prompt and the
runtime `prompt` argument as the first user message. The reply is returned
along with token + latency telemetry the eval cache + audit hooks consume.

Selection / model pinning:

  build_runtime("claude-agent-sdk")                       # default model
  build_runtime("claude-agent-sdk", model="claude-sonnet-4-6")  # pinned

Authentication:

  ANTHROPIC_API_KEY=...                                   # via env
  ClaudeAgentSDKAdapter(api_key="sk-ant-...")             # via constructor

The adapter delegates HTTP and JSON to the existing `AnthropicBackend`
(stdlib `urllib`) so the base install stays dependency-light. Replacing the
backend with the official `anthropic` SDK is a one-line swap when streaming
or tool-use lands; the AgentRuntime contract does not change.

Why this is named "claude-agent-sdk" rather than just "anthropic": the
runtime is *agent-shaped* — it carries skill state, instrumentation, and is
the substrate Mellea's PolicyManifest hooks attach to. The name describes
the role in the lifecycle, not the underlying SDK import.
"""

from __future__ import annotations

import os

from skillctl.agentskills import SkillFrontmatter
from skillctl.llm.anthropic import AnthropicBackend
from skillctl.llm.base import LLMBackendError

from .runtime import AgentRuntime, RuntimeResponse


class ClaudeAgentSDKAdapter(AgentRuntime):
    """Claude-backed AgentRuntime.

    Construction is cheap — the API key is validated on the first activation,
    not at construction time, so `list_runtimes` is safe to call in
    environments without keys. A missing key surfaces as a `RuntimeResponse`
    with an error trace rather than crashing the eval run.
    """

    name = "claude-agent-sdk"

    DEFAULT_MODEL = "claude-sonnet-4-6"
    DEFAULT_MAX_TOKENS = 4096

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.0,
        backend: AnthropicBackend | None = None,
    ) -> None:
        self._model = (
            model
            or os.environ.get("BBSCTL_RUNTIME_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or self.DEFAULT_MODEL
        )
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._backend = backend or AnthropicBackend(
            api_key=api_key, default_model=self._model
        )

    def activate(self, skill: SkillFrontmatter, prompt: str) -> RuntimeResponse:
        system = self._build_system_prompt(skill)
        skill_name = skill.name or "unknown"

        try:
            response = self._backend.complete(
                prompt=prompt,
                model=self._model,
                system=system,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except LLMBackendError as exc:
            return RuntimeResponse(
                activated_skill=skill_name,
                reply=f"[runtime error] {exc}",
                trace=[
                    f"[{self.name}] received prompt: {prompt!r}",
                    f"[{self.name}] backend error: {exc}",
                ],
                metadata={
                    "error": str(exc),
                    "model": self._model,
                    "backend": self._backend.name,
                },
            )

        trace = [
            f"[{self.name}] received prompt: {prompt!r}",
            f"[{self.name}] activated: {skill_name}",
            f"[{self.name}] model: {response.model}",
            f"[{self.name}] tokens: "
            f"in={response.prompt_tokens}, out={response.completion_tokens}",
            f"[{self.name}] latency: {response.latency_ms}ms",
        ]

        return RuntimeResponse(
            activated_skill=skill_name,
            reply=response.text,
            trace=trace,
            metadata={
                "model": response.model,
                "backend": response.backend,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "latency_ms": response.latency_ms,
                "skill_description_chars": len(skill.description or ""),
                "body_chars": len(skill.body),
            },
        )

    def _build_system_prompt(self, skill: SkillFrontmatter) -> str:
        """Assemble the system prompt the model sees per activation.

        The skill description provides routing context; the body provides
        the instructions. This mirrors how agentskills.io-compatible hosts
        (Claude Code's plugin system) feed a skill into a conversation.
        """
        parts: list[str] = []
        if skill.description:
            parts.append(
                f"# Skill activated: {skill.name or 'skill'}\n\n"
                f"## When to use\n{skill.description}\n"
            )
        parts.append(f"## Instructions\n\n{skill.body}")
        return "\n".join(parts).strip()


__all__ = ["ClaudeAgentSDKAdapter"]
