"""`bbsctl fetch` — download a skill from an external source and audit it.

Supports three source formats:

    # skills.sh catalog URL
    bbsctl fetch https://www.skills.sh/vercel-labs/agent-skills/web-design-guidelines

    # GitHub repo + skill name
    bbsctl fetch https://github.com/vercel-labs/agent-skills --skill web-design-guidelines

    # GitHub shorthand
    bbsctl fetch vercel-labs/agent-skills/web-design-guidelines

Skills are downloaded to `.bulbasaur/staging/<skill-name>/` and
automatically audited. The user reviews the report, then installs
with `bbsctl add --staged <skill-name>`.

No skill is trusted until the developer explicitly installs it.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from skillctl.audit.runner import AuditRunner
from skillctl.messaging import FrameworkError, emit, info

_STAGING_DIR = ".bulbasaur/staging"

_SKILLS_SH_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?skills\.sh/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<skill>[^/?#]+)"
)

_GITHUB_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/?#]+)"
)

_SHORTHAND_PATTERN = re.compile(
    r"^(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo>[a-zA-Z0-9_.-]+)"
    r"/(?P<skill>[a-zA-Z0-9_-]+)$"
)


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "fetch",
        help="Download and audit an external skill before installing",
        description=(
            "Fetch a skill from a catalog (skills.sh), GitHub repository, "
            "or local path. Downloads to a staging area and runs an automatic "
            "trust audit. Install after review with `bbsctl add --staged`."
        ),
    )
    p.add_argument(
        "source",
        help=(
            "Skill source: skills.sh URL, GitHub URL, "
            "owner/repo/skill shorthand, or local directory path"
        ),
    )
    p.add_argument(
        "--skill",
        default=None,
        help=(
            "Skill name within a multi-skill repository "
            "(required for GitHub URLs without a skill path)"
        ),
    )
    p.add_argument(
        "--dir",
        default=None,
        help="Project directory (default: current directory)",
    )
    p.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Audit output format (default: text)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    project_dir = Path(args.dir).resolve() if args.dir else Path.cwd()
    source = args.source.strip()

    parsed = _parse_source(source, skill_override=args.skill)
    if parsed is None:
        emit(FrameworkError(
            summary=f"cannot parse source: {source}",
            fix=(
                "Supported formats:\n"
                "  bbsctl fetch https://www.skills.sh/owner/repo/skill-name\n"
                "  bbsctl fetch https://github.com/owner/repo --skill skill-name\n"
                "  bbsctl fetch owner/repo/skill-name\n"
                "  bbsctl fetch ./path/to/local/skill"
            ),
        ))
        return 1

    owner, repo, skill_name, is_local = parsed

    if is_local:
        return _fetch_local(Path(source), project_dir, args.output)

    return _fetch_github(
        owner=owner,
        repo=repo,
        skill_name=skill_name,
        project_dir=project_dir,
        output_format=args.output,
    )


def _parse_source(
    source: str,
    *,
    skill_override: str | None,
) -> tuple[str, str, str, bool] | None:
    """Parse the source into (owner, repo, skill_name, is_local).

    Returns None if the source format is not recognized.
    """
    if Path(source).exists() and Path(source).is_dir():
        name = Path(source).resolve().name
        return ("", "", name, True)

    m = _SKILLS_SH_PATTERN.match(source)
    if m:
        return (m.group("owner"), m.group("repo"), m.group("skill"), False)

    m = _GITHUB_PATTERN.match(source)
    if m:
        owner, repo = m.group("owner"), m.group("repo")
        rest = source[m.end():].strip("/")
        if rest:
            skill = rest.split("/")[0]
            return (owner, repo, skill, False)
        if skill_override:
            return (owner, repo, skill_override, False)
        return None

    m = _SHORTHAND_PATTERN.match(source)
    if m:
        return (m.group("owner"), m.group("repo"), m.group("skill"), False)

    return None


def _fetch_local(
    skill_path: Path,
    project_dir: Path,
    output_format: str,
) -> int:
    """Stage a local skill directory and audit it."""
    skill_path = skill_path.resolve()
    skill_name = skill_path.name

    if not (skill_path / "SKILL.md").exists():
        emit(FrameworkError(
            summary=f"no SKILL.md in {skill_path}",
            fix="Point to a directory that contains a SKILL.md file.",
        ))
        return 1

    staging = project_dir / _STAGING_DIR / skill_name
    staging.parent.mkdir(parents=True, exist_ok=True)
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(skill_path, staging)

    info(f"Staged {skill_name} at {staging}")
    return _audit_staged(staging, skill_name, output_format)


def _fetch_github(
    *,
    owner: str,
    repo: str,
    skill_name: str,
    project_dir: Path,
    output_format: str,
) -> int:
    """Clone a GitHub repo (sparse) and extract the skill directory."""
    repo_url = f"https://github.com/{owner}/{repo}.git"
    info(f"Fetching {skill_name} from {owner}/{repo} ...")

    with tempfile.TemporaryDirectory(prefix="bbsctl-fetch-") as tmp:
        tmp_path = Path(tmp)

        repo_dir = tmp_path / "repo"

        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none",
             "--sparse", repo_url, str(repo_dir)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            # Fallback: try a regular shallow clone (some repos don't support sparse).
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(repo_dir)],
                capture_output=True, text=True, timeout=120,
            )

        if result.returncode != 0:
            emit(FrameworkError(
                summary=f"git clone failed for {repo_url}",
                detail=result.stderr.strip()[:500],
                fix=(
                    "Check that the repository exists and is public, "
                    "or that you have git credentials configured."
                ),
            ))
            return 1

        _sparse_checkout(repo_dir, skill_name)

        skill_dir = _find_skill_dir(repo_dir, skill_name)
        if skill_dir is None:
            emit(FrameworkError(
                summary=f"skill `{skill_name}` not found in {owner}/{repo}",
                fix=(
                    "Check the skill name. It should be a directory "
                    f"containing SKILL.md. Try browsing "
                    f"https://github.com/{owner}/{repo}"
                ),
            ))
            return 1

        staging = project_dir / _STAGING_DIR / skill_name
        staging.parent.mkdir(parents=True, exist_ok=True)
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(skill_dir, staging)

    info(f"Staged {skill_name} at {staging}")
    return _audit_staged(staging, skill_name, output_format)


def _sparse_checkout(repo_dir: Path, skill_name: str) -> None:
    """Enable sparse checkout and pull only the skill directory."""
    subprocess.run(
        ["git", "sparse-checkout", "init", "--cone"],
        cwd=repo_dir, capture_output=True, text=True, timeout=30,
    )
    subprocess.run(
        ["git", "sparse-checkout", "set",
         skill_name, f"skills/{skill_name}"],
        cwd=repo_dir, capture_output=True, text=True, timeout=30,
    )
    subprocess.run(
        ["git", "checkout"],
        cwd=repo_dir, capture_output=True, text=True, timeout=30,
    )


def _find_skill_dir(repo_dir: Path, skill_name: str) -> Path | None:
    """Locate the skill directory — could be at repo root or nested."""
    candidates = [
        repo_dir / skill_name,
        repo_dir / "skills" / skill_name,
    ]

    for p in repo_dir.rglob("SKILL.md"):
        if p.parent.name == skill_name and p.parent not in candidates:
            candidates.append(p.parent)

    for candidate in candidates:
        if candidate.is_dir() and (candidate / "SKILL.md").exists():
            return candidate

    return None


def _audit_staged(
    staging: Path,
    skill_name: str,
    output_format: str,
) -> int:
    """Run audit on the staged skill and print the report."""
    info("")
    info(f"{'=' * 60}")
    info(f"  Trust audit for: {skill_name}")
    info(f"{'=' * 60}")
    info("")

    runner = AuditRunner(staging)
    report = runner.run()

    if output_format == "json":
        print(report.format_json())
    else:
        info(f"Verdict: {report.verdict}  (worst: {report.worst_severity.name})")
        info("")
        info(report.format_text())

        if report.worst_severity.value >= 3:
            info("Action required before trusting this skill:")
            for f in report.all_findings:
                if f.severity.value >= 3:
                    info(f"  * {f.title}")
                    if f.recommendation:
                        info(f"    -> {f.recommendation}")
            info("")

    info("Next steps:")
    if report.worst_severity.value >= 4:
        info("  This skill has trust-blocking issues. Do NOT install.")
        info(f"  Review the skill at: {staging}")
    elif report.worst_severity.value >= 3:
        info(f"  1. Review the skill at: {staging}")
        info("  2. If acceptable, install with:")
        info(f"     bbsctl add --staged {skill_name}")
    else:
        info("  Install with:")
        info(f"     bbsctl add --staged {skill_name}")

    return 0 if report.worst_severity.value < 4 else 1


__all__ = ["register", "run"]
