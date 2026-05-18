"""Unit tests for the agentskills.io rule implementations.

These match the published spec at https://agentskills.io/specification — any
divergence is a bug. If the spec is ambiguous, the test is the source of truth
for our interpretation.
"""

from __future__ import annotations

import pytest

from skillctl.agentskills.rules import (
    AgentSkillsValidationError,
    validate_compatibility,
    validate_description,
    validate_metadata,
    validate_name,
)


class TestValidateName:
    @pytest.mark.parametrize(
        "valid_name",
        ["pdf-processing", "data-analysis", "code-review", "a", "skill1", "x" * 64],
    )
    def test_accepts_valid_names(self, valid_name):
        validate_name(valid_name)

    @pytest.mark.parametrize(
        "invalid_name,expected_code",
        [
            ("PDF-Processing", "pattern"),  # uppercase
            ("-pdf", "pattern"),  # leading hyphen
            ("pdf-", "pattern"),  # trailing hyphen
            ("pdf--processing", "pattern"),  # consecutive hyphens
            ("my_skill", "pattern"),  # underscore
            ("", "length"),  # empty
            ("x" * 65, "length"),  # too long
        ],
    )
    def test_rejects_invalid_names(self, invalid_name, expected_code):
        with pytest.raises(AgentSkillsValidationError) as exc_info:
            validate_name(invalid_name)
        assert exc_info.value.code == expected_code
        assert exc_info.value.fix is not None  # error-message contract

    def test_parent_dir_must_match(self):
        with pytest.raises(AgentSkillsValidationError) as exc_info:
            validate_name("hello-skill", parent_dir="something-else")
        assert exc_info.value.code == "parent_mismatch"


class TestValidateDescription:
    def test_accepts_typical_description(self):
        validate_description("A friendly skill for greeting the user when they say hello.")

    def test_rejects_empty(self):
        with pytest.raises(AgentSkillsValidationError) as exc_info:
            validate_description("")
        assert exc_info.value.code == "empty"

    def test_rejects_whitespace_only(self):
        with pytest.raises(AgentSkillsValidationError) as exc_info:
            validate_description("   \n  ")
        assert exc_info.value.code == "empty"

    def test_rejects_too_long(self):
        with pytest.raises(AgentSkillsValidationError) as exc_info:
            validate_description("x" * 1025)
        assert exc_info.value.code == "length"

    def test_accepts_exactly_1024(self):
        validate_description("x" * 1024)


class TestValidateCompatibility:
    def test_none_is_ok(self):
        validate_compatibility(None)

    def test_typical_value(self):
        validate_compatibility("Designed for Claude Code (or similar products)")

    def test_rejects_too_long(self):
        with pytest.raises(AgentSkillsValidationError):
            validate_compatibility("x" * 501)


class TestValidateMetadata:
    def test_none_is_ok(self):
        validate_metadata(None)

    def test_dict_with_arbitrary_keys(self):
        validate_metadata({"author": "team", "version": "1.0"})

    def test_metadata_instructions_caps_at_2048(self):
        # We adopt MCP Composer's 2048-char cap for metadata.instructions
        # (mcp-composer-analysis §6) — portability.
        validate_metadata({"instructions": "x" * 2048})

        with pytest.raises(AgentSkillsValidationError) as exc_info:
            validate_metadata({"instructions": "x" * 2049})
        assert exc_info.value.code == "length"

    def test_metadata_must_be_dict(self):
        with pytest.raises(AgentSkillsValidationError):
            validate_metadata(["not", "a", "dict"])
