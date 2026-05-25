"""Phase 2 marketplace module.

Provides:
  GitMarketplace    — read/publish against a Git/filesystem marketplace directory
  LockFile          — read/write skills.lock (ADR 0011)
  init_marketplace  — scaffold a new marketplace directory

Phase 3 adds the MCP Composer federation client (ADR 0012). That is a
separate module (marketplace/mcp_composer.py); nothing in this package
depends on it today.
"""

from .git_marketplace import GitMarketplace, MarketplaceEntry
from .lock import LockFile, LockPlugin

__all__ = [
    "GitMarketplace",
    "LockFile",
    "LockPlugin",
    "MarketplaceEntry",
]
