"""MockAgent — deterministic, no-LLM agent runtime for local development and tests.

The mock loads a skill's frontmatter and body, applies a tiny deterministic
"interpretation" of the body to produce a reply, and emits a trace that mirrors
what a real runtime would log. It is intentionally not smart — its job is to
demonstrate the framework's plumbing, not to do useful inference.

Real runtimes (Claude Agent SDK, Claude Code, MCP, LangGraph) land in Phase 4
and slot into the same AgentRuntime interface.
"""

from __future__ import annotations

import re

from skillctl.agentskills import SkillFrontmatter

from .runtime import AgentRuntime, RuntimeResponse


class MockAgent(AgentRuntime):
    """A deterministic mock agent for local development.

    Activation logic: extract the first `Reply with: "<text>"` directive from
    the body, or fall back to the first non-empty paragraph. No LLM call.
    """

    name = "mock-agent"

    _REPLY_DIRECTIVE = re.compile(r'Reply\s+with[:\s]+"([^"]+)"', re.IGNORECASE)

    def activate(self, skill: SkillFrontmatter, prompt: str) -> RuntimeResponse:
        trace = [
            f"[{self.name}] received prompt: {prompt!r}",
            f"[{self.name}] activated: {skill.name}",
        ]

        reply = self._extract_reply(skill.body)
        trace.append(f"[{self.name}] reply: {reply}")

        return RuntimeResponse(
            activated_skill=skill.name or "unknown",
            reply=reply,
            trace=trace,
            metadata={
                "agent": self.name,
                "skill_description_chars": len(skill.description or ""),
                "body_chars": len(skill.body),
            },
        )

    def _extract_reply(self, body: str) -> str:
        """Pull the first `Reply with: "..."` from the body, or use the first paragraph."""
        match = self._REPLY_DIRECTIVE.search(body)
        if match:
            return match.group(1).strip()

        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return "(no body content)"


__all__ = ["MockAgent"]
