"""Error-contract lint test.

The DX charter (framework-build-plan.md §0.2) requires ≥ 90% of user-facing
FrameworkError instances to carry a `fix=` argument. This test grep-walks the
codebase and fails if coverage drops below the threshold.

Why a lint test rather than runtime instrumentation: errors that never trigger
in tests are exactly the ones most likely to ship with a missing Fix line.
The lint sees every construction site, run-time path or not.

Exemptions: a construction site with `# error-contract: no-fix` on the same
line (or the immediately preceding line) is excluded from the denominator.
Use this sparingly — for internal-error placeholders that genuinely can't
provide a remediation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


SKILLCTL_ROOT = Path(__file__).resolve().parents[1] / "src" / "skillctl"
COVERAGE_THRESHOLD = 0.90
EXEMPTION_MARKER = "error-contract: no-fix"


def _iter_python_sources() -> list[Path]:
    """All .py files under skillctl/src/skillctl, excluding tests."""
    return sorted(p for p in SKILLCTL_ROOT.rglob("*.py") if "/tests/" not in str(p))


# Match `FrameworkError(` and capture the contents up to the balanced close paren.
# We use a simple state machine because regexes can't balance parens.
def _find_framework_error_calls(source: str) -> list[tuple[int, str]]:
    """Return [(line_number, full_call_text)] for each FrameworkError(...) construction.

    Line number is 1-based and points at the line with `FrameworkError(`.
    """
    calls: list[tuple[int, str]] = []
    needle = "FrameworkError("
    idx = 0
    while True:
        pos = source.find(needle, idx)
        if pos == -1:
            return calls

        # Skip definitions/imports — only count constructions.
        line_start = source.rfind("\n", 0, pos) + 1
        line_prefix = source[line_start:pos].strip()
        if line_prefix.startswith(("class ", "def ", "import ", "from ")) or "= FrameworkError" in line_prefix and "(" not in line_prefix:
            idx = pos + len(needle)
            continue

        # Walk forward, balancing parens, ignoring those inside strings.
        start = pos + len(needle)
        depth = 1
        i = start
        in_string = False
        string_char = ""
        escape = False
        while i < len(source) and depth > 0:
            ch = source[i]
            if escape:
                escape = False
            elif in_string:
                if ch == "\\":
                    escape = True
                elif ch == string_char:
                    in_string = False
            else:
                if ch in ("'", '"'):
                    in_string = True
                    string_char = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        full_call = source[pos:i]
        line_no = source.count("\n", 0, pos) + 1
        calls.append((line_no, full_call))
        idx = i


def _is_exempted(source: str, call_line: int) -> bool:
    """Check whether the construction site is exempted from the contract."""
    lines = source.splitlines()
    if call_line - 1 < len(lines) and EXEMPTION_MARKER in lines[call_line - 1]:
        return True
    if call_line - 2 >= 0 and EXEMPTION_MARKER in lines[call_line - 2]:
        return True
    return False


def _has_fix_argument(call_text: str) -> bool:
    """Heuristic: the call text contains `fix=` as a keyword argument."""
    # Match `fix=` at the start of an argument (after `(` or `,`), possibly after whitespace/newlines.
    return bool(re.search(r"(?:\(|,)\s*fix\s*=", call_text))


@pytest.fixture(scope="module")
def call_sites() -> list[tuple[Path, int, str, bool, bool]]:
    """Discover every FrameworkError construction site across the package.

    Returns a list of (path, line_number, call_text, has_fix, exempted) tuples.
    """
    sites: list[tuple[Path, int, str, bool, bool]] = []
    for path in _iter_python_sources():
        source = path.read_text(encoding="utf-8")
        if "FrameworkError" not in source:
            continue
        for line_no, call in _find_framework_error_calls(source):
            sites.append(
                (
                    path,
                    line_no,
                    call,
                    _has_fix_argument(call),
                    _is_exempted(source, line_no),
                )
            )
    return sites


def test_at_least_one_framework_error_site_exists(call_sites):
    """Sanity check — the test would silently pass on an empty codebase."""
    assert len(call_sites) > 0, (
        "no FrameworkError construction sites found; the test setup is broken"
    )


def test_fix_coverage_meets_dx_charter(call_sites):
    """≥ 90% of non-exempted FrameworkError sites must carry a fix= argument."""
    non_exempt = [s for s in call_sites if not s[4]]
    if not non_exempt:
        pytest.skip("all FrameworkError sites are exempted (suspicious; investigate)")

    with_fix = [s for s in non_exempt if s[3]]
    coverage = len(with_fix) / len(non_exempt)

    missing = [(s[0].relative_to(SKILLCTL_ROOT), s[1]) for s in non_exempt if not s[3]]
    missing_repr = "\n  ".join(f"{p}:{n}" for p, n in missing)
    assert coverage >= COVERAGE_THRESHOLD, (
        f"FrameworkError fix= coverage is {coverage:.0%} (threshold: {COVERAGE_THRESHOLD:.0%}).\n"
        f"Sites missing a Fix line:\n  {missing_repr}\n"
        f"Either add a `fix=...` argument or mark with `# error-contract: no-fix`."
    )
