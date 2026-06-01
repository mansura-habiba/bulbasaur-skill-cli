"""LLMBackend factory — register/build by name.

Default backend selection order:
  1. `name` argument
  2. `BBSCTL_LLM_BACKEND` env var
  3. `ollama` (no API key required)

Adding a backend (LocalLlamaBackend, mlx, etc.) is one class + one registration.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from .anthropic import AnthropicBackend
from .base import LLMBackend
from .ollama import OllamaBackend
from .openai import OpenAIBackend

_REGISTRY: dict[str, Callable[[], LLMBackend]] = {
    "ollama": OllamaBackend,
    "anthropic": AnthropicBackend,
    "openai": OpenAIBackend,
}


def register_backend(name: str, factory: Callable[[], LLMBackend]) -> None:
    _REGISTRY[name] = factory


def list_backends() -> list[str]:
    return sorted(_REGISTRY.keys())


def build_backend(name: str | None = None) -> LLMBackend:
    """Build the configured backend.

    Resolution: argument → env var → ollama default.
    """
    resolved = (
        name
        or os.environ.get("BBSCTL_LLM_BACKEND")
        or "ollama"
    ).lower()
    factory = _REGISTRY.get(resolved)
    if factory is None:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"unknown LLM backend: {resolved!r}. Available: {available}"
        )
    return factory()


__all__ = ["build_backend", "list_backends", "register_backend"]
