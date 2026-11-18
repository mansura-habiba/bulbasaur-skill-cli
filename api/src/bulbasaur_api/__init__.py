"""Optional FastMCP API at repository root; independent of skillctl."""

from .app import create_app, mcp, validate_skill

__all__ = ["create_app", "mcp", "validate_skill"]
