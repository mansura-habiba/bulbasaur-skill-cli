"""Top-level CLI router for skillctl.

argparse-based for stdlib-only base install. Each subcommand lives in its own
module under `skillctl.commands` and exposes a `register(subparsers)` function
that wires it into the parser.

Adding a new subcommand:
  1. Write `skillctl/commands/<name>.py` with `register` and a `run` entry.
  2. Append the import + register call to `_COMMANDS` below.
"""

from __future__ import annotations

import argparse
import sys

from skillctl import __version__
from skillctl.commands import compile as compile_cmd
from skillctl.commands import new as new_cmd
from skillctl.commands import run as run_cmd


# Subcommand registration. Order here is the order shown in --help.
# Each entry is a module exposing register(subparsers).
_COMMANDS = [
    new_cmd,
    compile_cmd,
    run_cmd,
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillctl",
        description=(
            "Bulbasaur skill framework CLI. Design, compile, validate, deploy, and "
            "evaluate agent skills like production code."
        ),
        epilog=(
            "More: https://github.com/bulbasaur/bulbasaur/tree/main/docs\n"
            "Quickstart: https://github.com/bulbasaur/bulbasaur/tree/main/quickstart"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"skillctl {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for module in _COMMANDS:
        module.register(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point — wired via `[project.scripts] skillctl = "skillctl.cli:main"`."""
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


if __name__ == "__main__":
    sys.exit(main())
