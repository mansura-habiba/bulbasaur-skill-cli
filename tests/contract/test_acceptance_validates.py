"""
test_acceptance_validates.py — contract tests for the acceptance specification layer.

This is the test-of-tests. It enforces:
  1. Every acceptance.yaml validates against acceptance.schema.yaml
  2. Every case in every acceptance.yaml has a test_id pointing to a test that exists
  3. Every invariant has a property_test pointing to a file that exists
  4. Task cards that reference `acceptance.spec` point at a real, ratified spec
  5. Anti-pattern checks: tests/contract/ files don't have orphan assertions (assertions
     not traceable to a case_id via comment)

Run locally:
    pytest tests/contract/test_acceptance_validates.py -v
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_SCHEMA = REPO_ROOT / ".governance" / "acceptance.schema.yaml"
ACCEPTANCE_DIR = REPO_ROOT / ".governance" / "acceptance"


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def _format_errors(errors) -> str:
    return "\n".join(
        f"  - at {'/'.join(map(str, err.path)) or '<root>'}: {err.message}"
        for err in errors
    )


def _acceptance_paths() -> list[Path]:
    return [Path(p) for p in glob.glob(str(ACCEPTANCE_DIR / "*.acceptance.yaml"))]


@pytest.fixture(scope="module")
def acceptance_validator() -> Draft202012Validator:
    return Draft202012Validator(_load_yaml(ACCEPTANCE_SCHEMA))


# -----------------------------------------------------------------------------
# Schema-level validation
# -----------------------------------------------------------------------------


def test_acceptance_schema_is_well_formed() -> None:
    schema = _load_yaml(ACCEPTANCE_SCHEMA)
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    "path", _acceptance_paths(), ids=lambda p: p.name
)
def test_acceptance_spec_validates(
    path: Path, acceptance_validator: Draft202012Validator
) -> None:
    doc = _load_yaml(path)
    errors = sorted(acceptance_validator.iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, (
        f"\nAcceptance spec failed schema validation: {path}\n"
        f"{_format_errors(errors)}\n"
    )


# -----------------------------------------------------------------------------
# Cross-reference checks — beyond what the schema can enforce
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", _acceptance_paths(), ids=lambda p: p.name
)
def test_capability_pointer_resolves(path: Path) -> None:
    """Each acceptance spec's `capability` field must point at an existing file."""
    doc = _load_yaml(path)
    cap_path = REPO_ROOT / doc["capability"]
    assert cap_path.exists(), (
        f"\n{path}: capability '{doc['capability']}' does not resolve to a file.\n"
    )


@pytest.mark.parametrize(
    "path", _acceptance_paths(), ids=lambda p: p.name
)
def test_every_case_has_evidence_test_id(path: Path) -> None:
    """
    Every case must have an evidence.test_id pointing at a real test path.
    The test function does not need to exist YET (it may be authored as part of the task),
    but the *file path* must resolve, otherwise the case is orphaned.
    """
    doc = _load_yaml(path)
    missing: list[str] = []
    for case in doc.get("cases", []):
        ev = case.get("evidence") or {}
        test_id = ev.get("test_id")
        if not test_id:
            missing.append(f"case '{case['id']}' has no evidence.test_id")
            continue
        # Format is `path/to/file.py::test_function`
        if "::" not in test_id:
            missing.append(f"case '{case['id']}' evidence.test_id missing '::test_name' suffix")
            continue
        file_part = test_id.split("::", 1)[0]
        # Tests may not yet exist when spec is `draft`. Only enforce existence at `ratified`.
        if doc.get("status") == "ratified":
            if not (REPO_ROOT / file_part).exists():
                missing.append(
                    f"case '{case['id']}' evidence.test_id points at missing file: {file_part}"
                )
    assert not missing, (
        f"\n{path} — evidence problems:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )


@pytest.mark.parametrize(
    "path", _acceptance_paths(), ids=lambda p: p.name
)
def test_every_invariant_has_property_test_file(path: Path) -> None:
    """Each invariant's property_test must point at a file that will exist at ratification."""
    doc = _load_yaml(path)
    if doc.get("status") != "ratified":
        pytest.skip("Spec not yet ratified; deferred-file references permitted in draft.")
    missing = []
    for inv in doc.get("invariants", []) or []:
        test_path = inv.get("property_test", "")
        if not test_path:
            missing.append(f"invariant '{inv['id']}' missing property_test")
            continue
        file_part = test_path.split("::", 1)[0]
        if not (REPO_ROOT / file_part).exists():
            missing.append(f"invariant '{inv['id']}' property_test file missing: {file_part}")
    assert not missing, (
        f"\n{path} — invariant problems:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )


@pytest.mark.parametrize(
    "path", _acceptance_paths(), ids=lambda p: p.name
)
def test_every_case_has_a_kind(path: Path) -> None:
    """Trivial but load-bearing — without `kind`, coverage analysis is meaningless."""
    doc = _load_yaml(path)
    no_kind = [c["id"] for c in doc.get("cases", []) if not c.get("kind")]
    assert not no_kind, f"Cases missing `kind`: {no_kind}"


# -----------------------------------------------------------------------------
# Coverage assertions — the spec's case-kind profile is queryable
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", _acceptance_paths(), ids=lambda p: p.name
)
def test_ratified_spec_has_both_positive_and_negative_cases(path: Path) -> None:
    """
    A spec without negative cases is incomplete by definition. This catches the
    AI-writes-only-happy-path failure mode at the spec level, not at the test level.
    """
    doc = _load_yaml(path)
    if doc.get("status") != "ratified":
        pytest.skip("Coverage profile enforced at ratification.")
    kinds = {c.get("kind") for c in doc.get("cases", [])}
    assert "positive" in kinds, f"{path}: ratified spec must have at least one positive case."
    assert "negative" in kinds, f"{path}: ratified spec must have at least one negative case."


# -----------------------------------------------------------------------------
# Task-card → acceptance spec linkage
# -----------------------------------------------------------------------------


def _task_card_paths_with_spec_ref() -> list[Path]:
    paths = []
    for p in glob.glob(str(REPO_ROOT / ".governance" / "examples" / "task-card.example.yaml")):
        paths.append(Path(p))
    for p in glob.glob(str(REPO_ROOT / ".governance" / "tasks" / "*.yaml")):
        paths.append(Path(p))
    return paths


@pytest.mark.parametrize(
    "path", _task_card_paths_with_spec_ref(), ids=lambda p: p.name
)
def test_task_card_acceptance_spec_ref_resolves(path: Path) -> None:
    """If a task card references `acceptance.spec`, it must point at an existing acceptance file."""
    doc = _load_yaml(path)
    spec_ref = (doc.get("acceptance") or {}).get("spec")
    if not spec_ref:
        pytest.skip("Task does not reference an acceptance spec.")
    spec_path = REPO_ROOT / spec_ref
    assert spec_path.exists(), (
        f"\n{path}: acceptance.spec '{spec_ref}' does not resolve to a file."
    )


@pytest.mark.parametrize(
    "path", _task_card_paths_with_spec_ref(), ids=lambda p: p.name
)
def test_task_card_case_ids_exist_in_spec(path: Path) -> None:
    """If a task card lists case_ids, they must all exist in the referenced acceptance spec."""
    doc = _load_yaml(path)
    acceptance = doc.get("acceptance") or {}
    spec_ref = acceptance.get("spec")
    case_ids = acceptance.get("case_ids") or []
    if not (spec_ref and case_ids):
        pytest.skip("Task does not narrow to specific case_ids.")
    spec_doc = _load_yaml(REPO_ROOT / spec_ref)
    available = {c["id"] for c in spec_doc.get("cases", [])}
    missing = [cid for cid in case_ids if cid not in available]
    assert not missing, (
        f"\n{path}: case_ids not found in {spec_ref}: {missing}\n"
        f"Available: {sorted(available)}"
    )


# -----------------------------------------------------------------------------
# Anti-pattern lint on tests/contract/ — catches AI test smells
# -----------------------------------------------------------------------------


_TEST_FILES = [
    Path(p) for p in glob.glob(str(REPO_ROOT / "tests" / "contract" / "*.py"))
    if not p.endswith("__init__.py")
]


@pytest.mark.parametrize(
    "path",
    _TEST_FILES,
    ids=lambda p: p.name,
)
def test_no_orphan_assertions_in_contract_tests(path: Path) -> None:
    """
    Heuristic: every test function in tests/contract/ should reference a case_id in either
    its name, docstring, or a comment. Tests with no spec linkage are the AI-invented-test
    anti-pattern. This is a heuristic — false positives are filed as `# spec-exempt: <reason>`.
    """
    src = path.read_text()
    # Find every `def test_...` function.
    test_funcs = re.findall(r"def (test_\w+)\(", src)
    if not test_funcs:
        pytest.skip("No test functions in this file.")
    orphans: list[str] = []
    for fn_name in test_funcs:
        # Extract the function body (cheaply — until next top-level def or EOF).
        pattern = rf"def {fn_name}\([^)]*\)[^:]*:\s*((?:(?!^def\s).|\n)+)"
        m = re.search(pattern, src, re.MULTILINE)
        body = m.group(1) if m else ""
        # Accept any one of: case-id-like kebab string, "# spec-exempt:", "case_id", "case:".
        if re.search(r"[a-z][a-z0-9-]+[a-z0-9]", body) and (
            "case_id" in body
            or "spec-exempt" in body
            or "case:" in body
            or re.search(r"#.*[a-z][a-z0-9-]+[a-z0-9]", body)
        ):
            continue
        # Tests that are themselves part of the contract-of-contracts (i.e. THIS file's tests
        # of the schema layer) are exempt.
        if fn_name.startswith(("test_acceptance_", "test_task_card_", "test_capability_",
                               "test_every_", "test_no_", "test_ratified_")):
            continue
        orphans.append(fn_name)
    assert not orphans, (
        f"\n{path}: test functions with no apparent case_id linkage:\n"
        + "\n".join(f"  - {o}" for o in orphans)
        + "\nAdd a comment referencing the case_id from the acceptance spec, or mark `# spec-exempt: <reason>`.\n"
    )
