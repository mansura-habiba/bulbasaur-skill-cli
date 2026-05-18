"""Factory for AgentRuntime adapters.

Phase 1 ships only `mock`. Phase 4 adds `claude-agent-sdk`, `claude-code`.
Phase 6 adds `mcp`, `langgraph`. Adding a runtime is a matter of registering
its constructor here and adding it to the `--runtime` choices in the CLI.
"""

from __future__ import annotations

from typing import Callable

from .mock import MockAgent
from .runtime import AgentRuntime


_REGISTRY: dict[str, Callable[[], AgentRuntime]] = {
    "mock": MockAgent,
}


def register_runtime(name: str, factory: Callable[[], AgentRuntime]) -> None:
    """Register an AgentRuntime constructor under `name`."""
    _REGISTRY[name] = factory


def build_runtime(name: str = "mock") -> AgentRuntime:
    """Build a runtime by name. Defaults to the mock for the Phase 1 quickstart."""
    factory = _REGISTRY.get(name)
    if factory is None:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"unknown runtime: {name!r}. Available: {available}")
    return factory()


def list_runtimes() -> list[str]:
    return sorted(_REGISTRY.keys())


__all__ = ["build_runtime", "register_runtime", "list_runtimes"]
