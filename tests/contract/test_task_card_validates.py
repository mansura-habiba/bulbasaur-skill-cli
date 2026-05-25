"""
test_task_card_validates.py — v0.1 contract test

The first executable enforcement point of the governance framework. Validates every task card
YAML in the repo against `.governance/task-card.schema.yaml` and every capability spec against
`.governance/capability-spec.schema.yaml`.

When this test fails in CI, the PR cannot merge — even before a human reviewer is assigned.

Run locally:
    pytest tests/contract/test_task_card_validates.py -v
"""
from __future__ import annotations

import glob
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_CARD_SCHEMA = REPO_ROOT / ".governance" / "task-card.schema.yaml"
CAPABILITY_SCHEMA = REPO_ROOT / ".governance" / "capability-spec.schema.yaml"


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def _format_errors(errors) -> str:
    """Render JSON Schema validation errors in a human + AI readable form."""
    lines = []
    for err in errors:
        loc = "/".join(map(str, err.path)) or "<root>"
        lines.append(f"  - at {loc}: {err.message}")
    return "\n".join(lines)


@pytest.fixture(scope="module")
def task_card_validator() -> Draft202012Validator:
    return Draft202012Validator(_load_yaml(TASK_CARD_SCHEMA))


@pytest.fixture(scope="module")
def capability_validator() -> Draft202012Validator:
    return Draft202012Validator(_load_yaml(CAPABILITY_SCHEMA))


# -----------------------------------------------------------------------------
# Task card validation
# -----------------------------------------------------------------------------


def _task_card_paths() -> list[Path]:
    """All task card YAMLs the framework should validate."""
    patterns = [
        REPO_ROOT / ".governance" / "tasks" / "*.yaml",
        REPO_ROOT / ".governance" / "examples" / "task-card.example.yaml",
    ]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(p) for p in glob.glob(str(pattern)))
    return paths


@pytest.mark.parametrize("path", _task_card_paths(), ids=lambda p: p.name)
def test_task_card_validates_against_schema(
    path: Path, task_card_validator: Draft202012Validator
) -> None:
    """Every task card YAML must validate against the schema."""
    doc = _load_yaml(path)
    errors = sorted(task_card_validator.iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, (
        f"\nTask card failed schema validation: {path}\n"
        f"{_format_errors(errors)}\n"
    )


def test_task_card_schema_is_well_formed() -> None:
    """The schema itself must be a valid JSON Schema Draft 2020-12 document."""
    schema = _load_yaml(TASK_CARD_SCHEMA)
    Draft202012Validator.check_schema(schema)


# -----------------------------------------------------------------------------
# Capability spec validation
# -----------------------------------------------------------------------------


def _capability_paths() -> list[Path]:
    return [Path(p) for p in glob.glob(str(REPO_ROOT / ".governance" / "capabilities" / "*.yaml"))]


@pytest.mark.parametrize("path", _capability_paths(), ids=lambda p: p.name)
def test_capability_validates_against_schema(
    path: Path, capability_validator: Draft202012Validator
) -> None:
    """Every capability YAML must validate against the schema."""
    doc = _load_yaml(path)
    errors = sorted(capability_validator.iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, (
        f"\nCapability spec failed schema validation: {path}\n"
        f"{_format_errors(errors)}\n"
    )


def test_capability_schema_is_well_formed() -> None:
    """The capability schema itself must be a valid JSON Schema Draft 2020-12 document."""
    schema = _load_yaml(CAPABILITY_SCHEMA)
    Draft202012Validator.check_schema(schema)


# -----------------------------------------------------------------------------
# Cross-reference checks — the bits a schema alone can't enforce
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("path", _task_card_paths(), ids=lambda p: p.name)
def test_task_card_parent_capability_resolves(path: Path) -> None:
    """A task card's parent_capability must point at a file that exists."""
    doc = _load_yaml(path)
    parent = doc.get("links", {}).get("parent_capability")
    assert parent, f"{path} has no parent_capability"
    parent_path = REPO_ROOT / parent
    assert parent_path.exists(), (
        f"\n{path} references parent_capability '{parent}' which does not exist.\n"
        f"Either create the capability file at {parent_path}, or fix the path in the task card.\n"
    )


@pytest.mark.parametrize("path", _task_card_paths(), ids=lambda p: p.name)
def test_task_card_required_reading_files_exist(path: Path) -> None:
    """Every file in ai_context.required_reading must exist — the AI cannot read what isn't there."""
    doc = _load_yaml(path)
    required = doc.get("ai_context", {}).get("required_reading", [])
    missing = [r for r in required if not (REPO_ROOT / r).exists()]
    assert not missing, (
        f"\n{path}: ai_context.required_reading points at missing files:\n"
        + "\n".join(f"  - {m}" for m in missing)
        + "\nFix paths or remove from the list.\n"
    )
