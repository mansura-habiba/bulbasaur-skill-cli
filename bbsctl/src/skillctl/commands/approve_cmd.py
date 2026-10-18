"""`bbsctl approve` — human sign-off over the evidence manifest digest."""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import load_project_config
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.lifecycle.evidence import (
    assemble_evidence,
    latest_evidence_bundle,
    write_approval,
)
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "approve",
        help="Record human approval on the evidence bundle",
        description=(
            "Write approval.json over the current evidence manifest digest. "
            "Required at org+ strictness before publish."
        ),
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    p.add_argument(
        "--by",
        required=True,
        metavar="ID",
        help="Approver identity (local string or GitHub handle)",
    )
    p.add_argument(
        "--note",
        default="",
        help="Optional note recorded with the approval",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing skill directory.",
            )
        )
        return 2

    bundle = latest_evidence_bundle(skill_dir)
    if bundle is None or not (bundle / "manifest.json").exists():
        assemble_evidence(
            skill_dir, results=[], strictness=_strictness(skill_dir)
        )
        bundle = latest_evidence_bundle(skill_dir)

    if bundle is None:
        emit(
            FrameworkError(
                summary="no evidence bundle to approve",
                fix="Run `bbsctl pipeline` first to produce `.bbsctl/evidence/`.",
                docs="../docs/lifecycle.md",
            )
        )
        return 1

    path = write_approval(bundle, by=args.by, note=args.note)
    info(f"approval written: {path}")
    return 0


def _strictness(skill_dir: Path) -> Strictness:
    try:
        overlay = load_skill_yaml(skill_dir)
        if overlay is not None:
            return overlay.strictness
    except SkillYamlError:
        pass
    return load_project_config(skill_dir).default_strictness


__all__ = ["register", "run"]
