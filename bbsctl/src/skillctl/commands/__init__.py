"""CLI subcommand modules.

Each command is its own module exposing a `run(args)` entry point. The CLI
(skillctl/cli.py) wires argparse to these entry points.

Adding a new command is a matter of writing one module here and registering
it in cli.py — the command registry pattern keeps the entry-point router
small.
"""

from __future__ import annotations
