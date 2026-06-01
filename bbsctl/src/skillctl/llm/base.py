"""LLMBackend strategy interface.

A backend takes a prompt, returns an LLMResponse with the text plus telemetry.
Adapters do not stream by default — judges and short-prompt runtimes do not
need it; later phases can add a streaming method without breaking the contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    """One model call's normalized result."""

    text: str
    model: str               # canonical model identifier returned by the backend
    backend: str             # backend name (`ollama`, `anthropic`, etc.)
    prompt_tokens: int = 0   # 0 if backend does not report
    completion_tokens: int = 0
    latency_ms: int = 0
    metadata: dict = None    # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


class LLMBackendError(Exception):
    """Raised when a backend call fails for reasons the framework can recover from.

    Distinct from `Exception` so the LLMJudge can catch it specifically and
    surface a `JudgeVerdict(passed=False, reason="backend error: ...")` rather
    than crashing the eval run.
    """


class LLMBackend(ABC):
    """Strategy interface for model backends."""

    #: Short identifier used in CLI flags, env vars, and config files.
    name: str = "anonymous-backend"

    @abstractmethod
    def complete(
        self,
        *,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Send a prompt; return the text + telemetry.

        `model` overrides the backend's default model. `system` is an optional
        system prompt; backends without a system-prompt concept (raw OpenAI
        completions, e.g.) prepend it to the user prompt.
        """


__all__ = ["LLMBackend", "LLMBackendError", "LLMResponse"]
