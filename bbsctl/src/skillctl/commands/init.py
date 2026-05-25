"""`bbsctl init` — set up a Bulbasaur project in the current directory.

Writes (or updates) the `[tool.bulbasaur]` section in `pyproject.toml`
per ADR 0007. If `pyproject.toml` does not exist in the current directory,
the command suggests running `uv init` first.

After `bbsctl init` a developer can:
    bbsctl new my-skill --strictness team
    bbsctl validate --fast
    bbsctl marketplace init ./my-team-marketplace
"""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import ProjectConfig, render_toml_section
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "init",
        help="Set up a Bulbasaur project (writes [tool.bulbasaur] to pyproject.toml)",
        description=(
            "Initialise Bulbasaur project config in pyproject.toml. "
            "Safe to re-run — does not overwrite an existing [tool.bulbasaur] section."
        ),
    )
    p.add_argument(
        "--dir",
        default=None,
        help="Project directory (default: current directory)",
    )
    p.add_argument(
        "--strictness",
        default="local",
        choices=[s.value for s in Strictness],
        help="Default strictness for new skills in this project (default: local)",
    )
    p.add_argument(
        "--marketplace",
        default=None,
        metavar="PATH",
        help="Default marketplace path or URL to record in config",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing [tool.bulbasaur] section",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    pyproject = project_dir / "pyproject.toml"

    if not pyproject.exists():
        emit(
            FrameworkError(
                summary="pyproject.toml not found",
                detail=f"looked at: {pyproject}",
                fix=(
                    "Create a Python project first with `uv init` (recommended) or "
                    "`pip` + manually create pyproject.toml. "
                    "Bulbasaur adds config to an existing pyproject.toml; it does not "
                    "create one from scratch."
                ),
                docs="../docs/quickstart.md",
            )
        )
        return 1

    # Check if [tool.bulbasaur] already exists.
    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        emit(
            FrameworkError(
                summary="pyproject.toml parse error",
                detail=str(exc),
                fix="Fix the TOML syntax and re-run `bbsctl init`.",
            )
        )
        return 1

    already_configured = bool(data.get("tool", {}).get("bulbasaur"))
    if already_configured and not args.force:
        info("[tool.bulbasaur] already present in pyproject.toml")
        info("  Run `bbsctl init --force` to overwrite, or edit pyproject.toml directly.")
        info(f"  Source: {pyproject}")
        return 0

    config = ProjectConfig(
        version=1,
        default_strictness=Strictness.from_string(args.strictness),
        marketplace=args.marketplace,
    )
    toml_snippet = render_toml_section(config)

    if already_configured and args.force:
        # Remove the old [tool.bulbasaur] block and replace it.
        existing_text = pyproject.read_text(encoding="utf-8")
        new_text = _remove_tool_bulbasaur_section(existing_text) + toml_snippet
        pyproject.write_text(new_text, encoding="utf-8")
        info(f"Updated [tool.bulbasaur] in {pyproject}")
    else:
        # Append to the end of the file.
        with pyproject.open("a", encoding="utf-8") as fh:
            fh.write(toml_snippet)
        info(f"Added [tool.bulbasaur] to {pyproject}")

    info("")
    info("Next:")
    info("  bbsctl new my-skill --strictness team")
    info("  bbsctl validate --fast")
    return 0


def _remove_tool_bulbasaur_section(text: str) -> str:
    """Remove any existing [tool.bulbasaur*] tables from TOML text.

    Simple line-based removal: drops lines from the first `[tool.bulbasaur`
    header until the next top-level `[` section or end-of-file.
    """
    lines = text.splitlines(keepends=True)
    out = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[tool.bulbasaur"):
            in_section = True
            continue
        if in_section and stripped.startswith("[") and not stripped.startswith("[tool.bulbasaur"):
            in_section = False
        if not in_section:
            out.append(line)
    return "".join(out).rstrip() + "\n"


__all__ = ["register", "run"]
