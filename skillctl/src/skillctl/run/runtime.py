"""The AgentRuntime adapter interface.

Implementations of this interface (mock, Claude Agent SDK, Claude Code, MCP,
LangGraph) all expose the same shape so `skillctl run` does not care which
one is in use. Adding a runtime is a matter of one subclass plus a factory
registration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from skillctl.agentskills import SkillFrontmatter


@dataclass
class RuntimeResponse:
    """A skill activation result, normalized across runtimes."""

    activated_skill: str
    reply: str
    trace: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class AgentRuntime(ABC):
    """Strategy interface for agent runtimes.

    `activate(skill, prompt)` runs the skill against the prompt and returns a
    normalized response. Runtimes can also expose `name` for logging.
    """

    name: str = "anonymous-runtime"

    @abstractmethod
    def activate(self, skill: SkillFrontmatter, prompt: str) -> RuntimeResponse:
        """Activate the skill against the prompt and return the response."""


__all__ = ["AgentRuntime", "RuntimeResponse"]
