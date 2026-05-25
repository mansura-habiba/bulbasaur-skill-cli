"""BasicTriggerValidator — name + description form a useful activation signal.

The agent uses the skill's `name` and `description` to decide when to activate
it. Poor trigger signals (too generic, too short, no action word) cause
false activations or missed activations.

This is a lightweight heuristic check, not a semantic evaluation. The semantic
fuzzer (Phase 3) does the heavier evaluation. What we check here:

1. Name is not a generic reserved word that collides with common agent nouns.
2. Description is at least 20 characters (trivially short = no signal).
3. Description contains at least one action word in the first sentence
   (instructs the agent *what* to do, not just a label).
4. Description does not start with the skill name literally (redundant trigger).
"""

from __future__ import annotations

import io
import re
import time
from pathlib import Path

from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError
from skillctl.strictness import Strictness

from .base import Validator, ValidatorResult


def _read_frontmatter(skill_md: Path) -> tuple[str, str] | None:
    """Extract (name, description) from SKILL.md without full spec validation.

    The BasicTriggerValidator needs name + description to check trigger signal
    quality; it does not need to re-run the parent-directory check or other
    spec rules (those are the job of ParseFrontmatterStep / compile).
    Returns None if the file is missing, malformed, or has no usable content.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        return None

    fm_text = "\n".join(lines[1:closing])
    yaml = YAML(typ="safe")
    try:
        parsed = yaml.load(io.StringIO(fm_text)) or {}
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None

    name = str(parsed.get("name") or "")
    description = str(parsed.get("description") or "")
    return name, description

# Names so generic that trigger accuracy will be low.
_GENERIC_NAMES = frozenset(
    {
        "helper", "assistant", "agent", "tool", "skill", "task",
        "run", "execute", "do", "handle", "process", "get", "set",
        "create", "update", "delete", "list",
    }
)

# Verbs that make descriptions actionable. We look for at least one.
_ACTION_WORDS = re.compile(
    r"\b(generate|create|produce|write|summarize|summarise|translate|"
    r"analyse|analyze|extract|identify|classify|detect|plan|review|"
    r"compare|evaluate|convert|transform|explain|describe|search|"
    r"find|fetch|retrieve|send|respond|reply|recommend|suggest|"
    r"answer|solve|calculate|compute|check|verify|validate|"
    r"migrate|deploy|install|configure|optimize|optimise|monitor|"
    r"diagnose|triage|document|draft|format|parse|process|handle)\b",
    re.IGNORECASE,
)

_MIN_DESCRIPTION_LENGTH = 20


class BasicTriggerValidator(Validator):
    """Check name and description form a clear, non-ambiguous trigger signal."""

    name = "basic-trigger"

    def run(self, skill_dir: Path, strictness: Strictness) -> ValidatorResult:
        started = time.monotonic()
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        notes: list[str] = []

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            # ParseFrontmatterStep would have caught this; skip gracefully.
            notes.append("SKILL.md not found; skipping trigger check")
            return ValidatorResult(
                validator_name=self.name,
                passed=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                notes=notes,
            )

        fm = _read_frontmatter(skill_md)
        if fm is None:
            notes.append("Could not parse SKILL.md frontmatter; skipping trigger check")
            return ValidatorResult(
                validator_name=self.name,
                passed=True,
                duration_ms=int((time.monotonic() - started) * 1000),
                notes=notes,
            )

        skill_name = fm[0].strip().lower()
        description = fm[1].strip()

        # Check 1: generic name.
        base_name = skill_name.rstrip("s")  # simple singularize for the check
        if skill_name in _GENERIC_NAMES or base_name in _GENERIC_NAMES:
            warnings.append(
                FrameworkError(
                    summary=f"skill name `{fm[0]}` is too generic",
                    detail=(
                        "Generic names like 'helper', 'tool', 'assistant' produce poor "
                        "trigger accuracy — the agent cannot reliably decide when to activate."
                    ),
                    fix=(
                        "Use a more specific name that describes the skill's domain or action, "
                        "e.g. `incident-triage`, `cloud-cost-analyser`, `pr-reviewer`."
                    ),
                    docs="https://agentskills.io/specification#name-field",
                )
            )

        # Check 2: description length.
        if len(description) < _MIN_DESCRIPTION_LENGTH:
            errors.append(
                FrameworkError(
                    summary=(
                        f"description too short "
                        f"({len(description)} chars, minimum {_MIN_DESCRIPTION_LENGTH})"
                    ),
                    detail="A short description gives the agent no activation signal.",
                    fix=(
                        "Write a full sentence explaining what this skill does and when to use it. "
                        "Example: 'Triages incoming production incidents by severity and generates "
                        "an initial runbook entry.'"
                    ),
                    docs="https://agentskills.io/specification#description-field",
                )
            )

        # Check 3: description contains an action word.
        elif not _ACTION_WORDS.search(description):
            warnings.append(
                FrameworkError(
                    summary="description lacks an action verb",
                    detail=(
                        "The description should tell the agent *what* the skill does. "
                        f"No recognizable action word found in: {description[:80]!r}"
                    ),
                    fix=(
                        "Start or include a verb describing the skill's action: "
                        "'Generates ...', 'Extracts ...', 'Summarizes ...', etc."
                    ),
                )
            )

        # Check 4: description starts with the skill name (redundant trigger).
        if description.lower().startswith(skill_name):
            warnings.append(
                FrameworkError(
                    summary="description starts with the skill name (redundant trigger signal)",
                    detail=(
                        f"Starting with `{fm.name}` is redundant — the agent already knows "
                        "the name. The description should add context, not repeat it."
                    ),
                    fix="Rephrase: start with the action or domain instead of the skill name.",
                )
            )

        notes.append(
            f"trigger check: name={fm[0]!r} desc_len={len(description)} "
            f"action_found={bool(_ACTION_WORDS.search(description))}"
        )

        return ValidatorResult(
            validator_name=self.name,
            passed=not errors,
            duration_ms=int((time.monotonic() - started) * 1000),
            errors=errors,
            warnings=warnings,
            notes=notes,
        )


__all__ = ["BasicTriggerValidator"]
