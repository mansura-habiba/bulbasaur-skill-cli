"""Optional, transport-only HTTP interface for the Bulbasaur skill library."""

from .app import create_app

__all__ = ["create_app"]
