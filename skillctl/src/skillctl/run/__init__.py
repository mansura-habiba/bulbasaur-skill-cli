"""The run module — execute a skill against a target agent runtime.

The pluggable shape (Phase 1 ships the mock; Phase 4+ adds real runtimes):

  AgentRuntime (ABC)        the adapter interface
  MockAgent                 the Phase 1 default — deterministic, no model call
  ClaudeAgentSDKAdapter     Phase 4 — real Claude Agent SDK
  ClaudeCodeAdapter         Phase 4 — Claude Code plugin host
  MCPAdapter                Phase 6 — exposes the skill as an MCP tool
  LangGraphAdapter          Phase 6 — exposes the skill as a LangGraph node
  RuntimeFactory            builds the right adapter from a config

Phase 1 just needs `skillctl run` to load a SKILL.md, hand it to the mock
agent, accept a sample prompt, and print the result. That is enough to
demonstrate the five-minute promise.
"""

from .runtime import AgentRuntime, RuntimeResponse
from .mock import MockAgent
from .factory import build_runtime

__all__ = ["AgentRuntime", "RuntimeResponse", "MockAgent", "build_runtime"]
