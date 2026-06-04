"""Top-level CLI router for bbsctl (Python module `skillctl`; ADR 0006).

argparse-based for stdlib-only base install. Each subcommand lives in its own
module under `skillctl.commands` and exposes a `register(subparsers)` function
that wires it into the parser.

Adding a new subcommand:
  1. Write `skillctl/commands/<name>.py` with `register` and a `run` entry.
  2. Append the import + register call to `_COMMANDS` below.

Top-level exception handling (Phase 1 friction-audit F5): every uncaught
exception below the subcommand `run()` boundary is captured here and converted
into a FrameworkError-shaped output so users never see a raw Python traceback.
Bare exceptions are framework bugs; we acknowledge that explicitly and give
the user something they can copy into a bug report.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

from skillctl import __version__
from skillctl.commands import (
    audit_cmd,
    classify_cmd,
    eval_cmd,
    gateway_cmd,
    marketplace_cmd,
    policy_cmd,
    risk_cmd,
    strictness_cmd,
)
from skillctl.dotenv import load_dotenv
from skillctl.commands import compile as compile_cmd
from skillctl.commands import (
    fetch as fetch_cmd,
)
from skillctl.commands import init as init_cmd
from skillctl.commands import install as install_cmd
from skillctl.commands import new as new_cmd
from skillctl.commands import publish as publish_cmd
from skillctl.commands import run as run_cmd
from skillctl.commands import validate as validate_cmd
from skillctl.messaging import FrameworkError, emit

# Subcommand registration. Order here is the order shown in --help.
# Each entry is a module exposing register(subparsers).
_COMMANDS = [
    # Project setup
    init_cmd,
    # Authoring
    new_cmd,
    strictness_cmd,
    # Build
    compile_cmd,
    validate_cmd,
    run_cmd,
    eval_cmd,
    # Governance
    policy_cmd,
    risk_cmd,
    classify_cmd,
    gateway_cmd,
    # Distribution
    marketplace_cmd,
    publish_cmd,
    install_cmd,
    # Trust & external skills
    fetch_cmd,
    audit_cmd,
]


# Common OS-error classes get tailored Fix hints. Anything not in this map
# falls through to the generic "framework bug" wrapper at the bottom of main().
_OS_ERROR_FIXES: dict[type[OSError], str] = {
    PermissionError: (
        "The framework cannot read or write the affected path. "
        "Check the path's ownership and permissions (`ls -la <path>`), or "
        "choose a path you have write access to via `--output <dir>`."
    ),
    FileNotFoundError: (
        "The path the command needs does not exist. "
        "Verify the path you passed and re-run."
    ),
    IsADirectoryError: (
        "The framework expected a file but found a directory. "
        "Pass the file path explicitly."
    ),
    NotADirectoryError: (
        "The framework expected a directory but found a file. "
        "Pass a directory path explicitly."
    ),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bbsctl",
        description=(
            "Bulbasaur skill framework CLI. Design, compile, validate, deploy, and "
            "evaluate agent skills like production code."
        ),
        epilog=(
            "More: https://github.com/mansura-habiba/bulbasaur-skill-cli/tree/main/docs\n"
            "Quickstart: https://github.com/mansura-habiba/bulbasaur-skill-cli/tree/main/quickstart"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"bbsctl {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for module in _COMMANDS:
        module.register(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point — wired via `[project.scripts] bbsctl = "skillctl.cli:main"`."""
    # Load a project-local `.env` (if present) BEFORE any subcommand parses
    # configuration. Shell-set env vars take precedence over `.env`. The
    # loader is forgiving — a missing or malformed file does not crash
    # startup. Disable by setting BBSCTL_SKIP_DOTENV=1.
    if not os.environ.get("BBSCTL_SKIP_DOTENV"):
        load_dotenv()

    parser = _build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0

    try:
        return int(func(args) or 0)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except SystemExit:
        # argparse's --help / errors raise SystemExit; let it propagate.
        raise
    except OSError as exc:
        # Filesystem / permission / IO errors get a tailored Fix; the framework
        # never lets these escape as a raw traceback (friction-audit F5).
        emit(_os_error_to_framework_error(exc, command=args.command))
        return 1
    except Exception as exc:
        # Any other unexpected exception is a framework bug. Surface a
        # FrameworkError-shaped message that still tells the user what to do.
        emit(_unexpected_exception_to_framework_error(exc, command=args.command))
        return 2


def _os_error_to_framework_error(exc: OSError, *, command: str | None) -> FrameworkError:
    """Convert an OSError to a FrameworkError with a copy-pasteable Fix."""
    fix = _OS_ERROR_FIXES.get(type(exc))
    if fix is None:
        # Fall back to the OSError errno description if we have one.
        errno_name = getattr(exc, "errno", None)
        fix = (
            f"OSError with errno={errno_name}. "
            "Check the path involved and your permissions; re-run with `BBSCTL_DEBUG=1` "
            "to see the full traceback."
        )

    path = getattr(exc, "filename", None) or getattr(exc, "filename2", None) or "<unknown>"

    return FrameworkError(
        summary=f"{type(exc).__name__}: {exc}",
        detail=f"path: {path}; command: bbsctl {command or '<unknown>'}",
        fix=fix,
        docs="../docs/troubleshooting.md",
    )


def _unexpected_exception_to_framework_error(
    exc: Exception, *, command: str | None
) -> FrameworkError:
    """Convert an unexpected exception to a FrameworkError, preserving the traceback."""
    tb = traceback.format_exc()
    debug_enabled = os.environ.get("BBSCTL_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    if debug_enabled:
        # Print the full traceback to stderr so debuggers see it; the
        # FrameworkError below is still emitted for the structured Fix line.
        print(tb, file=sys.stderr)

    return FrameworkError(
        summary=f"unexpected error in bbsctl {command or '<unknown>'} (framework bug)",
        detail=f"{type(exc).__name__}: {exc}",
        fix=(
            "This is a framework bug, not a user error. "
            "Re-run with `BBSCTL_DEBUG=1` to see the full traceback, then file an "
            "issue with the command you ran, the SKILL.md (if relevant), and the traceback."
        ),
        docs="https://github.com/mansura-habiba/bulbasaur-skill-cli/issues",
    )


if __name__ == "__main__":
    sys.exit(main())
