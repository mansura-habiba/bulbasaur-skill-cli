"""Auto-detect provenance from git state.

Helper for `bbsctl publish`. Reads `git rev-parse HEAD`, `git remote get-url
origin`, and `git symbolic-ref HEAD` to populate the `provenance` block on
a skill.yaml whose author left those fields empty. Subprocess-based so the
framework stays git-binary-agnostic (no `dulwich` / `gitpython` dependency).

Behaviour:

  detect_git_provenance(skill_dir) → Provenance
    Walks from skill_dir upward to find the enclosing git repo. Returns an
    empty `Provenance` if no repo is found or if any subprocess fails.
    Never raises — provenance detection is best-effort.

The publish pipeline can compare the detected `commit_sha` against the
`commit_sha` declared in `skill.yaml` to detect smuggled artifacts (the
declared sha doesn't match the working tree's actual state).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from skillctl.skill_yaml import Provenance


def detect_git_provenance(skill_dir: Path) -> Provenance:
    """Best-effort: extract source_repo + commit_sha + branch from git state.

    Returns an empty Provenance if anything fails (no git repo, no remote
    configured, subprocess error, etc.). Never raises.
    """
    repo_root = _find_git_root(skill_dir)
    if repo_root is None:
        return Provenance()

    return Provenance(
        source_repo=_normalize_remote_url(_git_get_remote_url(repo_root)),
        commit_sha=_git_get_head_sha(repo_root),
        source_repo_branch=_git_get_branch(repo_root),
    )


# ── internals ───────────────────────────────────────────────────────────────


def _find_git_root(start: Path) -> Path | None:
    """Walk upward looking for a `.git` directory (or file, for submodules)."""
    cur = start.resolve()
    while True:
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _git(cwd: Path, *args: str) -> str:
    """Run `git <args>` in `cwd`, return stripped stdout or empty on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _git_get_head_sha(repo: Path) -> str:
    sha = _git(repo, "rev-parse", "HEAD")
    return sha if _is_hex_sha(sha) else ""


def _git_get_remote_url(repo: Path) -> str:
    return _git(repo, "config", "--get", "remote.origin.url")


def _git_get_branch(repo: Path) -> str:
    """Return the symbolic ref short-form (e.g. `main`) or empty if detached."""
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


def _is_hex_sha(s: str) -> bool:
    return bool(s) and bool(_SHA_RE.match(s))


def _normalize_remote_url(url: str) -> str:
    """Normalize SSH-form to https-form for display.

    git@github.com:acme/foo.git → github.com/acme/foo
    https://github.com/acme/foo.git → github.com/acme/foo
    Returns the input unchanged if no recognized pattern matches.
    """
    if not url:
        return ""
    # SSH form: git@host:owner/repo.git
    ssh_match = re.match(r"^[\w.-]+@([\w.-]+):(.+?)(?:\.git)?$", url)
    if ssh_match:
        host, path = ssh_match.group(1), ssh_match.group(2)
        return f"{host}/{path}"
    # HTTPS form.
    https_match = re.match(r"^https?://([\w.-]+)/(.+?)(?:\.git)?/?$", url)
    if https_match:
        host, path = https_match.group(1), https_match.group(2)
        return f"{host}/{path}"
    return url


__all__ = ["detect_git_provenance"]
