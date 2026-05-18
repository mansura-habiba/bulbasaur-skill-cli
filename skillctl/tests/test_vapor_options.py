"""Vapor-options lint test.

Friction-audit F10: argparse `choices=...` for the `--strictness`, `--target`,
and `--runtime` flags must match the set of implementations actually registered.
If the CLI advertises a level/target/runtime with no real backing, users get
silent success on a no-op — which is exactly how F2/F3 happened.

This test instantiates each subcommand's argparse parser and walks every
choice-style option, asserting each value resolves to a real implementation
in the corresponding factory/registry.
"""

from __future__ import annotations

import argparse

import pytest

from skillctl.publish.factory import list_targets
from skillctl.run.factory import list_runtimes
from skillctl.strictness import Strictness, supported_levels


def _build_subcommand_parser(module) -> argparse.ArgumentParser:
    """Build the standalone subparser exposed by a commands/<name>.py module."""
    parser = argparse.ArgumentParser(prog="bbsctl")
    subparsers = parser.add_subparsers(dest="command")
    module.register(subparsers)
    return parser


def _choices_for(parser: argparse.ArgumentParser, command: str, flag: str) -> list[str]:
    """Extract the `choices=` list for a `--<flag>` option of a given subcommand."""
    sub_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    sub = sub_action.choices[command]
    for action in sub._actions:
        if flag in action.option_strings:
            return list(action.choices or [])
    return []


class TestStrictnessChoices:
    """`--strictness` choices match `supported_levels(<command>)` exactly."""

    @pytest.mark.parametrize(
        "command_module_path,command",
        [
            ("skillctl.commands.new", "new"),
            ("skillctl.commands.compile", "compile"),
            ("skillctl.commands.publish", "publish"),
        ],
    )
    def test_strictness_choices_match_registry(self, command_module_path, command):
        from importlib import import_module

        module = import_module(command_module_path)
        parser = _build_subcommand_parser(module)
        choices = _choices_for(parser, command, "--strictness")
        expected = supported_levels(command)
        assert choices == expected, (
            f"--strictness choices for `bbsctl {command}` disagree with "
            f"`supported_levels(\"{command}\")`:\n"
            f"  argparse choices: {choices}\n"
            f"  registry:         {expected}\n"
            f"Fix: update strictness._SUPPORTED or argparse choices=. See ADR-derived "
            f"docs/audits/phase-1.md F2/F3."
        )


class TestTargetChoices:
    """`--target` choices in `bbsctl publish` match the registered targets."""

    def test_publish_target_choices_match_registry(self):
        from skillctl.commands import publish as publish_cmd

        parser = _build_subcommand_parser(publish_cmd)
        choices = _choices_for(parser, "publish", "--target")
        expected = list_targets()
        assert sorted(choices) == sorted(expected), (
            f"--target choices for `bbsctl publish` disagree with registered targets:\n"
            f"  argparse choices: {choices}\n"
            f"  registry:         {expected}\n"
        )


class TestRuntimeChoices:
    """`--runtime` choices in `bbsctl run` match the registered runtimes."""

    def test_run_runtime_choices_match_registry(self):
        from skillctl.commands import run as run_cmd

        parser = _build_subcommand_parser(run_cmd)
        choices = _choices_for(parser, "run", "--runtime")
        expected = list_runtimes()
        assert sorted(choices) == sorted(expected), (
            f"--runtime choices for `bbsctl run` disagree with registered runtimes:\n"
            f"  argparse choices: {choices}\n"
            f"  registry:         {expected}\n"
        )


class TestStrictnessRegistryItself:
    """The Strictness enum + supported_levels registry are internally consistent."""

    def test_every_supported_level_is_a_real_enum_value(self):
        # Walks supported_levels for every known command and confirms each level
        # parses back to a Strictness enum member (no typo'd strings).
        for command in ("new", "compile", "publish"):
            for value in supported_levels(command):
                level = Strictness.from_string(value)
                assert level.value == value, f"value {value!r} did not round-trip"
