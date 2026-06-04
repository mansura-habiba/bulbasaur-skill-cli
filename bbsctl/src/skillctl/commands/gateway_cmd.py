"""`bbsctl gateway` — single security-gateway entry for CI.

Bundles three checks into one command + one report:

  1. `bbsctl validate --fast`   structural + permissions + ownership + policy + risk-matrix
  2. injection-corpus eval       if `evals/injection.json` is present (smoke mode)
  3. instruction classification  scans SKILL.md body fragments through the
                                 InstructionClassifier

Returns a single aggregated `GatewayReport` and a single exit code:

  0 = every gate passed
  1 = at least one gate failed
  2 = framework error (missing SKILL.md, malformed config, etc.)

Designed to be the CI/CD entrypoint: one job step that returns one signal.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from skillctl.agentskills import parse_skill_md
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.eval import EvalMode, EvalRunner
from skillctl.eval.loader import EvalLoadError
from skillctl.eval.reproducibility import (
    EvalConfigError,
    load_eval_config,
    merge_config,
)
from skillctl.instruction_classifier import (
    FragmentSource,
    HeuristicClassifier,
    InstructionClassifier,
    LLMInstructionClassifier,
)
from skillctl.llm import list_backends
from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import load_project_config
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness
from skillctl.validate import ValidateMode, ValidateRunner


@dataclass
class GatewayCheck:
    """One gate's outcome."""

    name: str
    passed: bool
    summary: str
    details: list[dict] = field(default_factory=list)


@dataclass
class GatewayReport:
    """Aggregated report from all three gates."""

    skill_dir: str
    strictness: str
    checks: list[GatewayCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "gateway",
        help="Run the full security gateway (validate + injection eval + classify).",
        description=(
            "One command, one signal. Runs the validator chain at FAST mode, "
            "the injection eval if a corpus exists, and the instruction "
            "classifier across SKILL.md body fragments. CI/CD entrypoint."
        ),
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory).",
    )
    p.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help="Override strictness (default: read from skill.yaml).",
    )
    p.add_argument(
        "--classifier",
        default="heuristic",
        choices=["heuristic", "llm"],
        help="Classifier backend (default: heuristic — no API key).",
    )
    p.add_argument(
        "--backend",
        default=None,
        choices=list_backends(),
        help="LLM backend when --classifier=llm.",
    )
    p.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="LLM model when --classifier=llm.",
    )
    p.add_argument(
        "--skip-eval",
        action="store_true",
        default=False,
        help="Skip the injection eval gate (useful when no corpus is committed).",
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json", "silent"],
        help="Output format (default: text).",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing directory or `cd` into the skill first.",
            )
        )
        return 2

    if not (skill_dir / "SKILL.md").exists():
        emit(
            FrameworkError(
                summary=f"SKILL.md not found at {skill_dir / 'SKILL.md'}",
                fix="Run `bbsctl new <name>` to scaffold a skill first.",
            )
        )
        return 2

    strictness = _resolve_strictness(skill_dir, args.strictness)
    report = GatewayReport(skill_dir=str(skill_dir), strictness=strictness.value)

    # ── Gate 1: validate ─────────────────────────────────────────────────
    report.checks.append(_run_validate_gate(skill_dir, strictness))

    # ── Gate 2: injection eval ───────────────────────────────────────────
    if not args.skip_eval:
        eval_gate = _run_eval_gate(skill_dir, strictness)
        if eval_gate is not None:
            report.checks.append(eval_gate)

    # ── Gate 3: instruction classification ───────────────────────────────
    report.checks.append(_run_classification_gate(skill_dir, args))

    # ── Output ───────────────────────────────────────────────────────────
    if args.output == "silent":
        return 0 if report.passed else 1

    if args.output == "json":
        sys.stdout.write(json.dumps(_report_to_dict(report), indent=2) + "\n")
        return 0 if report.passed else 1

    _print_report(report)
    return 0 if report.passed else 1


# ── gate runners ────────────────────────────────────────────────────────────


def _run_validate_gate(skill_dir: Path, strictness: Strictness) -> GatewayCheck:
    """Run the standard validator chain at FAST mode."""
    runner = ValidateRunner(skill_dir, strictness, mode=ValidateMode.FAST)
    result = runner.run()
    details = []
    for r in result.results:
        details.append(
            {
                "validator": r.validator_name,
                "passed": r.passed,
                "errors": [e.summary for e in r.errors],
                "warnings": [w.summary for w in r.warnings],
            }
        )
    return GatewayCheck(
        name="validate",
        passed=result.passed,
        summary=(
            f"validators: {sum(1 for r in result.results if r.passed)}/"
            f"{len(result.results)} passed"
        ),
        details=details,
    )


def _run_eval_gate(skill_dir: Path, strictness: Strictness) -> GatewayCheck | None:
    """Run the injection corpus in smoke mode if present.

    Returns None when no injection corpus exists — the gateway skips silently
    so the report stays clean for skills that don't carry one.
    """
    if not (skill_dir / "evals" / "injection.json").is_file():
        return None

    try:
        base_config = load_eval_config(skill_dir)
    except EvalConfigError as exc:
        return GatewayCheck(
            name="injection-eval",
            passed=False,
            summary=f"eval.config.yaml malformed: {exc.framework_error.summary}",
        )

    config = merge_config(base_config)  # use config-file defaults

    try:
        runner = EvalRunner(
            skill_dir,
            strictness,
            mode=EvalMode.SMOKE,
            config=config,
            suite_filter="injection",
        )
        report = runner.run()
    except (EvalLoadError, AgentSkillsValidationError) as exc:
        err = exc.framework_error if hasattr(exc, "framework_error") else None
        summary = err.summary if err else str(exc)
        return GatewayCheck(
            name="injection-eval",
            passed=False,
            summary=summary,
        )

    if not report.suites:
        return GatewayCheck(
            name="injection-eval",
            passed=True,
            summary="injection corpus present but had no cases",
        )

    suite = report.suites[0]
    return GatewayCheck(
        name="injection-eval",
        passed=report.passed,
        summary=(
            f"score={suite.score:.2f}  "
            f"({suite.passed_count}/{suite.total_count} cases passing)"
        ),
        details=[
            {
                "case_id": c.case_id,
                "passed": c.passed,
                "score": c.score,
            }
            for c in suite.cases
        ],
    )


def _run_classification_gate(
    skill_dir: Path, args: argparse.Namespace
) -> GatewayCheck:
    """Run the InstructionClassifier across SKILL.md body fragments.

    The body is treated as `skill_instruction` (trusted) — the classifier
    flags only those fragments that look like injection patterns the author
    accidentally pasted in. Mirrors the compile-time scan but with a
    semantic LLM check available.
    """
    classifier: InstructionClassifier
    if args.classifier == "llm":
        try:
            classifier = LLMInstructionClassifier(
                backend_name=args.backend, model=args.model
            )
        except Exception as exc:
            return GatewayCheck(
                name="classify",
                passed=False,
                summary=f"could not build LLM classifier: {exc}",
            )
    else:
        classifier = HeuristicClassifier()

    try:
        frontmatter = parse_skill_md(skill_dir / "SKILL.md")
    except AgentSkillsValidationError as exc:
        return GatewayCheck(
            name="classify",
            passed=False,
            summary=f"SKILL.md parse error: {exc.message}",
        )

    body = frontmatter.body or ""
    # Classify the body as a single fragment. Future enhancement: split by
    # paragraph and classify each (some paragraphs may quote attacks
    # legitimately; we'd preserve the same blockquote/code-fence skipping
    # as the compile-time scan).
    classification = classifier.classify(
        text=body, source=FragmentSource.SKILL_INSTRUCTION
    )

    # Note: the body is asserted as `skill_instruction` (trusted source). The
    # classifier doesn't flag matched patterns as untrusted-instruction in
    # that case — the gate fails only if matched patterns are non-empty AND
    # the developer hasn't documented them via blockquote/code-fence.
    has_patterns = bool(classification.matched_patterns)

    return GatewayCheck(
        name="classify",
        passed=not has_patterns,
        summary=(
            f"patterns_matched: {sorted(set(classification.matched_patterns))}"
            if has_patterns
            else "no injection-shaped patterns in body"
        ),
        details=[
            {
                "trust_level": classification.trust_level.value,
                "matched_patterns": list(classification.matched_patterns),
                "reasoning": classification.reasoning,
            }
        ],
    )


# ── output ──────────────────────────────────────────────────────────────────


def _print_report(report: GatewayReport) -> None:
    status = "PASSED" if report.passed else "FAILED"
    info(f"gateway @ {report.strictness}: {status}")
    info(f"  skill: {report.skill_dir}")
    info("")
    for c in report.checks:
        icon = "✓" if c.passed else "✗"
        info(f"  {icon} {c.name}: {c.summary}")
        if not c.passed:
            for d in c.details:
                if d.get("errors"):
                    for e in d["errors"]:
                        info(f"      ERROR: {e}")
                if d.get("warnings"):
                    for w in d["warnings"]:
                        info(f"      WARN:  {w}")


def _report_to_dict(report: GatewayReport) -> dict:
    return {
        "passed": report.passed,
        "skill_dir": report.skill_dir,
        "strictness": report.strictness,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "summary": c.summary,
                "details": c.details,
            }
            for c in report.checks
        ],
    }


def _resolve_strictness(skill_dir: Path, override: str | None) -> Strictness:
    if override:
        return Strictness.from_string(override)
    try:
        overlay = load_skill_yaml(skill_dir)
        if overlay is not None:
            return overlay.strictness
    except SkillYamlError:
        pass
    config = load_project_config(skill_dir)
    return config.default_strictness


__all__ = ["GatewayCheck", "GatewayReport", "register", "run"]
