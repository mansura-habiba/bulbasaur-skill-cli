"""`bbsctl policy` — manage policies.

Subcommands:

  bbsctl policy list                      # show bundled catalog + any local
  bbsctl policy show <ref>                # render one policy in human form
  bbsctl policy lint <path>               # validate the policy file itself
  bbsctl policy validate <ref> <skill>    # run a policy against a skill

`<ref>` accepts a catalog short name (`hipaa-baseline`), a local path
(`./policies/internal.yaml`), or an absolute path.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from skillctl.messaging import FrameworkError, emit, info
from skillctl.policy import (
    PolicyEngine,
    PolicyLoadError,
    load_policy,
    merge_policies,
)
from skillctl.policy.base import CheckOutcome
from skillctl.policy.catalog import (
    catalog_dir,
    list_catalog_names,
    resolve_catalog_path,
)
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "policy",
        help="Manage policies (list, show, lint, validate)",
        description=(
            "Bulbasaur policies are YAML files that declare what a skill must "
            "satisfy to be considered conformant at a given strictness rung. "
            "The framework ships an enforcement engine; the org ships the "
            "policy data."
        ),
    )
    sub = p.add_subparsers(dest="policy_command", metavar="<subcommand>")

    list_p = sub.add_parser(
        "list",
        help="List bundled catalog policies and any local policies under ./policies/",
    )
    list_p.add_argument(
        "--dir",
        default=".",
        help="Project directory (default: current).",
    )
    list_p.set_defaults(func=_run_list)

    show_p = sub.add_parser(
        "show",
        help="Render one policy in human-readable form.",
    )
    show_p.add_argument("ref", help="Catalog short name or path to a YAML file.")
    show_p.set_defaults(func=_run_show)

    lint_p = sub.add_parser(
        "lint",
        help="Validate the policy file itself (schema + metadata + dates).",
    )
    lint_p.add_argument("path", help="Path to a policy YAML file.")
    lint_p.set_defaults(func=_run_lint)

    validate_p = sub.add_parser(
        "validate",
        help="Run a policy against a skill and print the per-requirement results.",
    )
    validate_p.add_argument(
        "ref", help="Catalog short name or path to a policy YAML file."
    )
    validate_p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current).",
    )
    validate_p.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help="Strictness override (default: derived from skill.yaml).",
    )
    validate_p.set_defaults(func=_run_validate)

    p.set_defaults(func=_no_subcommand(p))


def _no_subcommand(parser: argparse.ArgumentParser):
    def _run(args: argparse.Namespace) -> int:
        parser.print_help()
        return 0

    return _run


# ── list ────────────────────────────────────────────────────────────────────


def _run_list(args: argparse.Namespace) -> int:
    info(f"Catalog policies (bundled at {catalog_dir()}):")
    for name in list_catalog_names():
        path = resolve_catalog_path(name)
        meta = _try_load_metadata(path)
        info(f"  {name}@{meta or '?'}")

    project_dir = Path(args.dir).resolve()
    local_dir = project_dir / "policies"
    if local_dir.is_dir():
        info("")
        info(f"Local policies under {local_dir}:")
        for path in sorted(local_dir.glob("*.yaml")):
            meta = _try_load_metadata(path)
            info(f"  {path.name}  ({meta or 'unknown'})")
    return 0


def _try_load_metadata(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        policy = load_policy(path)
        return policy.metadata.version
    except PolicyLoadError:
        return None


# ── show ────────────────────────────────────────────────────────────────────


def _run_show(args: argparse.Namespace) -> int:
    path = _resolve_ref(args.ref)
    if path is None:
        emit(
            FrameworkError(
                summary=f"policy not found: {args.ref!r}",
                fix=(
                    "Pass a bundled name (`bbsctl policy list`) or a path "
                    "(`./policies/foo.yaml`)."
                ),
            )
        )
        return 1

    try:
        policy = load_policy(path)
    except PolicyLoadError as exc:
        emit(exc.framework_error)
        return 1

    info(f"# {policy.metadata.name} @ {policy.metadata.version}")
    if policy.metadata.description:
        info(f"  {policy.metadata.description}")
    info(
        f"  effective: {policy.metadata.effective_date} → "
        f"{policy.metadata.expiry_date} | authority: {policy.metadata.authority or 'unset'}"
    )
    info(
        f"  applies_to_strictness: {list(policy.applies_to_strictness)}"
    )
    info("")
    info(f"Required artifacts: files={list(policy.required_artifacts.files)}, "
         f"dirs={list(policy.required_artifacts.directories)}")
    info(f"Ownership: required={list(policy.ownership.required_fields)}, "
         f"review_max_days={policy.ownership.last_reviewed_max_age_days}, "
         f"security_reviewer={policy.ownership.require_security_reviewer}")
    info(f"Eval: suites={list(policy.eval.required_suites)}, "
         f"pinned_injection={policy.eval.injection_corpus_pinned}, "
         f"snapshots={policy.eval.snapshots_required}, "
         f"judge_must_be_llm={policy.eval.judge_must_be_llm}")
    info(f"Permissions: deny_default={list(policy.permissions.require_default_deny)}, "
         f"forbidden_count={len(policy.permissions.forbidden_commands)}")
    info(f"Audit: retention_days={policy.audit.retention_days}, "
         f"fail_mode={policy.audit.fail_mode}, "
         f"tamper_evident={policy.audit.tamper_evident}")
    info(f"Approval: approvers={len(policy.approval.required_approvers)}, "
         f"sign_off_required={policy.approval.sign_off_yaml_required}")
    info(f"Cost: tokens_per_run={policy.cost.max_tokens_per_run}, "
         f"usd_per_month={policy.cost.max_cost_usd_per_month}")
    info("")
    info("Compliance frameworks:")
    for f in policy.compliance_frameworks:
        controls = ", ".join(f.controls) if f.controls else "(none listed)"
        info(f"  {f.id}: {controls}")
    return 0


# ── lint ────────────────────────────────────────────────────────────────────


def _run_lint(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    try:
        policy = load_policy(path)
    except PolicyLoadError as exc:
        emit(exc.framework_error)
        return 1

    issues: list[FrameworkError] = []
    if not policy.metadata.is_active():
        issues.append(
            FrameworkError(
                summary=(
                    f"policy `{policy.metadata.name}@{policy.metadata.version}` "
                    "is outside its effective window"
                ),
                detail=(
                    f"effective={policy.metadata.effective_date}, "
                    f"expiry={policy.metadata.expiry_date}"
                ),
                fix="Update effective_date / expiry_date in the policy file.",
            )
        )
    if not policy.metadata.effective_date:
        issues.append(
            FrameworkError(
                summary="policy missing `effective_date`",
                fix="Add `effective_date: YYYY-MM-DD` under `policy:`.",
            )
        )

    if issues:
        for issue in issues:
            emit(issue)
        return 1

    info(
        f"policy `{policy.metadata.name}@{policy.metadata.version}` lint: OK"
    )
    return 0


# ── validate ────────────────────────────────────────────────────────────────


def _run_validate(args: argparse.Namespace) -> int:
    path = _resolve_ref(args.ref)
    if path is None:
        emit(
            FrameworkError(
                summary=f"policy not found: {args.ref!r}",
                fix="Pass a bundled name or path.",
            )
        )
        return 1
    try:
        policy = load_policy(path)
    except PolicyLoadError as exc:
        emit(exc.framework_error)
        return 1

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing directory, or `cd` into the skill first.",
            )
        )
        return 2

    strictness = (
        Strictness.from_string(args.strictness)
        if args.strictness
        else _derive_strictness(skill_dir)
    )

    result = PolicyEngine(policy).validate(skill_dir, strictness)

    info(
        f"policy `{result.policy_name}@{result.policy_version}` @ {strictness.value}: "
        f"{'PASSED' if result.passed else 'FAILED'}"
    )
    info(
        f"  {result.passed_checks} pass · "
        f"{len(result.failures)} fail · "
        f"{len(result.warnings)} deferred  "
        f"({result.total_checks} total)"
    )
    info("")
    for check in result.checks:
        icon = {
            CheckOutcome.PASS: "✓",
            CheckOutcome.FAIL: "✗",
            CheckOutcome.SKIP: "·",
            CheckOutcome.UNKNOWN: "~",
        }[check.outcome]
        info(f"  {icon} [{check.section}] {check.requirement}")
        if check.detail:
            info(f"      {check.detail}")
        if check.fix and check.outcome == CheckOutcome.FAIL:
            info(f"      Fix: {check.fix}")
    return 0 if result.passed else 1


def _resolve_ref(ref: str) -> Path | None:
    catalog_path = resolve_catalog_path(ref)
    if catalog_path is not None:
        return catalog_path
    p = Path(ref)
    if p.is_file():
        return p.resolve()
    return None


def _derive_strictness(skill_dir: Path) -> Strictness:
    """Read skill.yaml to determine the strictness; default LOCAL on absence."""
    from skillctl.skill_yaml import SkillYamlError, load_skill_yaml

    try:
        overlay = load_skill_yaml(skill_dir)
    except SkillYamlError:
        return Strictness.LOCAL
    return overlay.strictness if overlay else Strictness.LOCAL


__all__ = ["register"]
