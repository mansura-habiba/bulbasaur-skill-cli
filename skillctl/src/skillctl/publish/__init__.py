"""The publish module — emit a Bulbasaur skill as a consumable artifact for a target.

A "target" is any system that can host or run the skill once published. Targets
are the adapter layer between Bulbasaur and the rest of the agent ecosystem.

Phase 1 ships:
  claude-code-local    a local marketplace directory loadable by stock Claude
                       Code via /plugin marketplace add ./<dir>

Phase 2-3 will add:
  claude-code-remote   push to a Git-backed marketplace (the org-tier path)
  mcp-composer         federate to an MCP Composer catalog (per mcp-composer-analysis.md)
  oci                  publish as an OCI artifact

Adding a target is one PublishTarget subclass + one register_target call. The
publish command surface and the user-facing CLI do not change.
"""

from .factory import build_target, list_targets, register_target
from .target import PublishResult, PublishTarget

__all__ = ["PublishResult", "PublishTarget", "build_target", "list_targets", "register_target"]
