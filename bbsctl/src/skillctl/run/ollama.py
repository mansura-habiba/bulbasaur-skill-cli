"""OllamaRuntime — agent runtime backed by a locally-served Ollama model.

The complement to `ClaudeAgentSDKAdapter`. Where the SDK adapter talks to
Anthropic's hosted Messages API, this adapter activates a skill against an
Ollama server (default `http://localhost:11434`). No API key required.

The skill's body is sent as the system prompt; the runtime `prompt` argument
becomes the user message. The reply, model id, token counts, and latency are
recorded on the `RuntimeResponse` for the eval cache and audit hooks.

Selection / model pinning:

  build_runtime("ollama")                                # default model from env
  build_runtime("ollama", model="qwen2.5:14b")           # pinned per-call

Configuration (highest priority wins):

  1. constructor `model=` / `host=`
  2. env `BBSCTL_RUNTIME_MODEL` / `OLLAMA_MODEL`
  3. env `OLLAMA_HOST`
  4. user/org config file (via `skillctl.user_config.llm_backend_config`)
  5. `OllamaRuntime.DEFAULT_MODEL` / `OllamaBackend.DEFAULT_HOST`

Errors:

  Constructor never raises — `list_runtimes` is safe to call without a
  running Ollama server. The first `activate()` returns a `RuntimeResponse`
  with `[runtime error] Ollama unreachable: …` if the server is down.
"""

from __future__ import annotations

import os

from skillctl.agentskills import SkillFrontmatter
from skillctl.llm.base import LLMBackendError
from skillctl.llm.ollama import OllamaBackend

from .runtime import AgentRuntime, RuntimeResponse


class OllamaRuntime(AgentRuntime):
    """Skill activation against a local Ollama model."""

    name = "ollama"

    DEFAULT_MODEL = OllamaBackend.DEFAULT_MODEL
    DEFAULT_MAX_TOKENS = 4096

    def __init__(
        self,
        *,
        model: str | None = None,
        host: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.0,
        backend: OllamaBackend | None = None,
    ) -> None:
        # Resolve model with explicit override → BBSCTL_RUNTIME_MODEL → backend default.
        resolved_model = (
            model
            or os.environ.get("BBSCTL_RUNTIME_MODEL")
            or os.environ.get("OLLAMA_MODEL")
            or self.DEFAULT_MODEL
        )
        self._model = resolved_model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._backend = backend or OllamaBackend(
            host=host, default_model=resolved_model
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
        """Same shape as `ClaudeAgentSDKAdapter`; keeps prompts comparable across
        runtimes so an eval run can swap runtimes without changing assertions."""
        parts: list[str] = []
        if skill.description:
            parts.append(
                f"# Skill activated: {skill.name or 'skill'}\n\n"
                f"## When to use\n{skill.description}\n"
            )
        parts.append(f"## Instructions\n\n{skill.body}")
        return "\n".join(parts).strip()


__all__ = ["OllamaRuntime"]
