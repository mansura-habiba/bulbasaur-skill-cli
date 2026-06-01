"""Factory for AgentRuntime adapters.

Phase 1 ships only `mock`. Phase 4 adds `claude-agent-sdk`, `claude-code`.
Phase 6 adds `mcp`, `langgraph`. Adding a runtime is a matter of registering
its constructor here and adding it to the `--runtime` choices in the CLI.
"""

from __future__ import annotations

from collections.abc import Callable

from .mock import MockAgent
from .runtime import AgentRuntime


def _build_claude_agent_sdk(
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
):
    """Lazy import so the base install stays dependency-light."""
    from .claude_agent_sdk import ClaudeAgentSDKAdapter

    return ClaudeAgentSDKAdapter(
        model=model, max_tokens=max_tokens, temperature=temperature
    )


_REGISTRY: dict[str, Callable[..., AgentRuntime]] = {
    "mock": MockAgent,
    "claude-agent-sdk": _build_claude_agent_sdk,
}


def register_runtime(name: str, factory: Callable[[], AgentRuntime]) -> None:
    """Register an AgentRuntime constructor under `name`."""
    _REGISTRY[name] = factory


def build_runtime(
    name: str = "mock",
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> AgentRuntime:
    """Build a runtime by name. Defaults to the mock for the Phase 1 quickstart.

    `model`, `max_tokens`, and `temperature` are forwarded to factories that
    accept them; factories that don't are called with the subset they accept.
    Keeps the contract forward-compatible without breaking simple adapters.
    """
    factory = _REGISTRY.get(name)
    if factory is None:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"unknown runtime: {name!r}. Available: {available}")

    # Build the kwargs the caller wants to pass; fall back progressively.
    kwargs: dict = {}
    if model:
        kwargs["model"] = model
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature

    if not kwargs:
        return factory()

    try:
        return factory(**kwargs)
    except TypeError:
        # Factory does not accept all of the kwargs — try with the most
        # important ones first, falling all the way back to no kwargs.
        for subset in (
            {k: kwargs[k] for k in ("model",) if k in kwargs},
            {},
        ):
            try:
                return factory(**subset) if subset else factory()
            except TypeError:
                continue
        return factory()


def list_runtimes() -> list[str]:
    return sorted(_REGISTRY.keys())


__all__ = ["build_runtime", "list_runtimes", "register_runtime"]
