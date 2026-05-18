"""Regression tests for the top-level exception wrapper in cli.main().

Friction-audit F5: filesystem and permission errors used to escape as raw
Python tracebacks, bypassing the FrameworkError contract. cli.main() now wraps
every uncaught exception and produces FrameworkError-shaped output.

These tests construct the failure conditions and assert the user sees:
  - An ERROR: line
  - A Fix: line (per the error-message contract)
  - No "Traceback (most recent call last)" line
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from skillctl.cli import main as cli_main


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _make_unwritable(path: Path) -> None:
    """Drop all permissions so a child mkdir fails. Restore in the fixture cleanup."""
    path.chmod(stat.S_IRUSR)  # read-only for owner, no write/exec


def test_publish_to_unwritable_output_produces_framework_error(workspace, capsys):
    # Set up a skill so publish gets past the SKILL.md guard.
    assert cli_main(["new", "hello-skill"]) == 0

    # Create a directory and lock it so the publish's mkdir fails.
    locked = workspace / "locked-out"
    locked.mkdir()
    _make_unwritable(locked)

    try:
        code = cli_main(["publish", "hello-skill", "--output", str(locked / "marketplace")])
    finally:
        # Restore so pytest's tmp_path cleanup can succeed.
        locked.chmod(stat.S_IRWXU)

    captured = capsys.readouterr()
    combined = captured.out + captured.err

    # The friction-audit-failing case: a raw traceback.
    assert "Traceback (most recent call last)" not in combined, (
        "publish to unwritable dir leaked a Python traceback; "
        "the top-level exception wrapper is supposed to convert it."
    )

    # The error-message-contract case: ERROR + Fix.
    assert "ERROR:" in combined
    assert "Fix:" in combined
    # The user should learn it was a permission/filesystem issue, not a Python crash.
    assert "PermissionError" in combined or "permission" in combined.lower()

    # The exit code reflects user error (1), not framework error (2).
    assert code == 1


def test_unexpected_exception_surfaces_framework_bug_message(workspace, monkeypatch, capsys):
    """When an unrelated exception fires, the wrapper labels it as a framework bug."""

    # Monkey-patch the new command to raise a contrived exception, simulating a bug.
    from skillctl.commands import new as new_cmd

    def boom(args):  # noqa: ARG001
        raise RuntimeError("contrived for test")

    monkeypatch.setattr(new_cmd, "run", boom)

    code = cli_main(["new", "hello-skill"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert "Traceback" not in combined, "framework-bug path also must not leak a traceback"
    assert "ERROR:" in combined
    assert "framework bug" in combined.lower()
    assert "Fix:" in combined
    assert "BBSCTL_DEBUG" in combined  # the doc-pointer is part of the Fix
    # Exit code 2 = framework error (distinct from 1 = user error)
    assert code == 2


def test_bbsctl_debug_env_prints_traceback(workspace, monkeypatch, capsys):
    """BBSCTL_DEBUG=1 surfaces the full traceback alongside the FrameworkError."""
    from skillctl.commands import new as new_cmd

    def boom(args):  # noqa: ARG001
        raise RuntimeError("contrived for traceback test")

    monkeypatch.setattr(new_cmd, "run", boom)
    monkeypatch.setenv("BBSCTL_DEBUG", "1")

    cli_main(["new", "hello-skill"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert "Traceback" in combined
    assert "contrived for traceback test" in combined
    # The FrameworkError still emits alongside the traceback.
    assert "ERROR:" in combined
    assert "Fix:" in combined
