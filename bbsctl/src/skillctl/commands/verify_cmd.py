"""`bbsctl verify` — recompute evidence digests and check approval coverage."""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.lifecycle.evidence import latest_evidence_bundle, verify_evidence


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "verify",
        help="Verify a evidence bundle",
        description=(
            "Recompute digests, check approval covers the current manifest, "
            "and (when a skill dir is given) that the skill hash still matches."
        ),
    )
    p.add_argument(
        "path",
        nargs="?",
        default=".",
        help=(
            "Evidence bundle directory, or a skill directory "
            "(uses latest `.bbsctl/evidence/*`). Default: ."
        ),
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    skill_dir: Path | None = None

    if (path / "manifest.json").is_file():
        bundle = path
    elif path.is_dir():
        skill_dir = path
        bundle = latest_evidence_bundle(path)
        if bundle is None:
            emit(
                FrameworkError(
                    summary="no evidence bundle found",
                    detail=f"looked under {path / '.bbsctl' / 'evidence'}",
                    fix="Run `bbsctl pipeline` to assemble an evidence bundle first.",
                    docs="../docs/lifecycle.md",
                )
            )
            return 1
    else:
        emit(
            FrameworkError(
                summary=f"path not found: {path}",
                fix="Pass a skill directory or an evidence bundle path.",
            )
        )
        return 2

    ok, errors = verify_evidence(bundle, skill_dir=skill_dir)
    if ok:
        info(f"verify: OK  ({bundle})")
        return 0

    emit(
        FrameworkError(
            summary="evidence bundle verification failed",
            detail="; ".join(errors),
            fix=(
                "Re-run `bbsctl pipeline`, then `bbsctl approve --by <id>` "
                "if SKILL.md changed after the last approval."
            ),
            docs="../docs/lifecycle.md",
        )
    )
    return 1


__all__ = ["register", "run"]
