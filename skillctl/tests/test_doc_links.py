"""Doc-link resolution lint test.

Friction-audit F11: every relative link in a shipped Markdown file must resolve
to an existing file on disk. The audit caught six links to `docs/recipes/...`,
`docs/spec-guidelines.md`, etc. that did not exist — each is a 404 for the next
new user reading the docs.

This test walks every `.md` file under the repo (excluding historical snapshots
and audit reports that intentionally describe broken links), extracts every
relative Markdown link, and asserts the target resolves.

External links (`https://...`, `http://...`, `mailto:...`) are not checked.
Anchor-only links (`#section`) are not checked.
Code-block contents are skipped (so `` ```bash uvx skillctl ... ``` `` is fine).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# Repo root resolved from this test file:
# skillctl/src/skillctl/../../../tests/test_doc_links.py → ../../.. = repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# Files intentionally NOT scanned. Historical snapshots and the audit report
# document the issues this test exists to prevent — including broken-link
# examples is part of their content.
SKIP_FILES = {
    "framework-build-plan.old.md",
    "old_mental_model.md",
    "mental-model-critique.md",
    "mellea-analysis.md",
    "mcp-composer-analysis.md",
    str(Path("docs") / "audits" / "phase-1.md"),
}

# Match Markdown links: [text](target). Captures the target only.
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Match fenced code blocks (``` or ~~~) so we can strip them before scanning.
_CODE_FENCE_PATTERN = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)


def _md_files() -> list[Path]:
    """All .md files under the repo, excluding skipped historical files."""
    skip_resolved = {REPO_ROOT / p for p in SKIP_FILES}
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(REPO_ROOT).parts)
        and p not in skip_resolved
    )


def _extract_links(text: str) -> list[str]:
    """Extract all Markdown link targets, ignoring code blocks."""
    stripped = _CODE_FENCE_PATTERN.sub("", text)
    return [match.group(2).strip() for match in _LINK_PATTERN.finditer(stripped)]


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "ftp://", "tel:"))


def _is_anchor_only(target: str) -> bool:
    return target.startswith("#")


def _is_inline_placeholder(target: str) -> bool:
    """Placeholder markers like `<repo-url>/...` are deliberate; don't lint."""
    return target.startswith(("<", "{{", "<repo"))


@pytest.fixture(scope="module")
def md_link_index() -> list[tuple[Path, str]]:
    """Discover every (source_file, link_target) pair worth checking."""
    pairs: list[tuple[Path, str]] = []
    for md in _md_files():
        text = md.read_text(encoding="utf-8")
        for target in _extract_links(text):
            # Strip an anchor suffix (`#section`) from the path part.
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            if _is_external(target) or _is_anchor_only(target) or _is_inline_placeholder(target):
                continue
            pairs.append((md, path_part))
    return pairs


def test_some_links_found(md_link_index):
    """Sanity check — the test would silently pass on an empty codebase."""
    assert len(md_link_index) > 0, "no Markdown links found; the test setup is broken"


def test_every_relative_link_resolves(md_link_index):
    """Every relative link in a shipped Markdown file must point at an existing file."""
    missing: list[tuple[str, str]] = []
    for source, target in md_link_index:
        # Resolve relative to the source file's directory.
        resolved = (source.parent / target).resolve()
        if not resolved.exists():
            rel_source = source.relative_to(REPO_ROOT)
            missing.append((str(rel_source), target))

    if missing:
        rendered = "\n  ".join(f"{src} → {tgt}" for src, tgt in missing)
        pytest.fail(
            f"{len(missing)} relative Markdown link(s) do not resolve:\n  {rendered}\n"
            "Either create the file, fix the link, or remove the link. "
            "See docs/audits/phase-1.md F6/F11."
        )
