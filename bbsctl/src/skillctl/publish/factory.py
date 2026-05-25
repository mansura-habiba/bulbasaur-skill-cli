"""Factory for PublishTarget adapters.

Targets are registered at import time. The CLI uses `list_targets()` to populate
`--target` choices and `build_target(name)` to construct one.

Adding a target:

  from skillctl.publish import register_target, PublishTarget
  class MyTarget(PublishTarget): ...
  register_target(MyTarget)
"""

from __future__ import annotations

from collections.abc import Callable

from .claude_code_local import ClaudeCodeLocalTarget
from .target import PublishTarget

_REGISTRY: dict[str, Callable[[], PublishTarget]] = {}


def register_target(target_cls: type[PublishTarget]) -> None:
    """Register a PublishTarget class under its `name`.

    Re-registering an existing name overwrites the previous registration —
    useful for tests that want to inject mock targets.
    """
    instance = target_cls()
    _REGISTRY[instance.name] = target_cls


def build_target(name: str) -> PublishTarget:
    """Construct a target by name."""
    cls = _REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"unknown publish target: {name!r}. Available: {available}")
    return cls()


def list_targets() -> list[str]:
    """List registered target names in alphabetical order."""
    return sorted(_REGISTRY.keys())


def target_description(name: str) -> str:
    """Return the registered target's `description` string, or empty if missing."""
    cls = _REGISTRY.get(name)
    if cls is None:
        return ""
    return cls().description


# Phase 1 targets — registered at module import.
register_target(ClaudeCodeLocalTarget)


__all__ = ["build_target", "list_targets", "register_target", "target_description"]
