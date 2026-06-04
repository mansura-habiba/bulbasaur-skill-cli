"""Minimal `.env` loader. Stdlib-only.

Why this exists: the rest of the framework reads configuration from env vars
(`ANTHROPIC_API_KEY`, `OLLAMA_HOST`, `BBSCTL_*`, etc.) using `os.environ`.
Developers expect to keep secrets and per-project overrides in a `.env`
file that loads automatically. Adding `python-dotenv` would pull in a
dependency just for this convenience; the format is simple enough to parse.

Loader behaviour:

  - Walks from the current working directory upward looking for a `.env` file
    (stops at filesystem root). The first one found wins.
  - Parses `KEY=VALUE` lines. Whitespace-trimmed. Optional `export ` prefix
    (so a developer can `source .env` from their shell too).
  - Strips surrounding single or double quotes from VALUE.
  - Ignores blank lines and `#` comments.
  - Does NOT override variables that are already set in `os.environ` — the
    shell-set values win. This matches `python-dotenv` semantics and lets CI
    overrides take precedence over developer-local files.

Call `load_dotenv()` once at CLI startup before any module reads from env.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_FILENAME = ".env"


def find_dotenv(
    *, start: Path | None = None, filename: str = _DEFAULT_FILENAME
) -> Path | None:
    """Walk from `start` (default: cwd) upward, return the first `.env` found.

    Stops at filesystem root. Returns None if no file is found.
    """
    cur = (start or Path.cwd()).resolve()
    while True:
        candidate = cur / filename
        if candidate.is_file():
            return candidate
        if cur.parent == cur:  # filesystem root
            return None
        cur = cur.parent


def load_dotenv(
    *,
    path: Path | None = None,
    override: bool = False,
    start: Path | None = None,
    filename: str = _DEFAULT_FILENAME,
) -> Path | None:
    """Load a `.env` file into `os.environ`.

    Resolution order for the path:
      1. Explicit `path=` argument
      2. `find_dotenv(start=start, filename=filename)`

    Returns the resolved path actually loaded, or None if no file was found.
    Never raises on malformed lines — they're silently skipped (the loader
    runs at startup and must not crash the CLI).

    `override=False` (default) keeps existing `os.environ` values. Set
    `override=True` only when the `.env` file is intended as a hard pin.
    """
    target = path if path is not None else find_dotenv(start=start, filename=filename)
    if target is None or not target.is_file():
        return None

    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    for raw_line in text.splitlines():
        key, value = _parse_line(raw_line)
        if key is None:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
    return target


def parse_dotenv_string(text: str) -> dict[str, str]:
    """Parse a `.env`-shaped string into a {key: value} dict.

    Exposed for tests and for libraries that want to inspect what would be
    set without mutating `os.environ`.
    """
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        key, value = _parse_line(raw_line)
        if key is not None:
            out[key] = value
    return out


def _parse_line(raw: str) -> tuple[str | None, str]:
    """Parse one `.env` line. Returns (None, "") for blank / comment lines.

    Accepts:
      KEY=value
      KEY = value
      export KEY=value
      KEY="value with spaces"
      KEY='single quoted'
      KEY=value # inline comment (everything after first unquoted # is ignored)
    """
    line = raw.strip()
    if not line or line.startswith("#"):
        return None, ""

    # Optional `export ` prefix.
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()

    if "=" not in line:
        return None, ""

    key, _, value = line.partition("=")
    key = key.strip()
    if not key or not _is_valid_key(key):
        return None, ""

    value = _strip_inline_comment(value.strip())
    value = _strip_quotes(value)
    return key, value


def _is_valid_key(key: str) -> bool:
    """A valid env-var key matches `[A-Za-z_][A-Za-z0-9_]*`."""
    if not key:
        return False
    if not (key[0].isalpha() or key[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in key)


def _strip_inline_comment(value: str) -> str:
    """Remove `#…` comments, but only when the `#` is not inside quotes."""
    if not value:
        return value
    in_single = False
    in_double = False
    for i, ch in enumerate(value):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return value[:i].rstrip()
    return value


def _strip_quotes(value: str) -> str:
    """Strip surrounding matching single or double quotes from a value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


__all__ = [
    "find_dotenv",
    "load_dotenv",
    "parse_dotenv_string",
]
