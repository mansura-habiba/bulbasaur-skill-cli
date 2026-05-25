"""`bbsctl eval` — run the behavioral eval corpus against a skill.

Reads `evals/*.json` from the skill directory. Each JSON file is one suite
(name = filename stem). The suite shape:

    {
      "skill_name": "...",
      "evals": [
        { "id": ..., "prompt": "...", "expected_output": "...",
          "files": [], "assertions": [...] }
      ]
    }

By default `bbsctl eval` runs the mock runtime + the heuristic judge so it
works without an API key. `--runtime` and `--judge` accept any factory-
registered adapter. Phase 4 adds the Claude Agent SDK runtime and the LLM
judge; the interface here does not change when they land.

Exit codes: 0 = every suite passed, 1 = at least one case failed,
2 = framework error (load failure, missing SKILL.md, etc.).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.eval import EvalMode, EvalReport, EvalRunner
from skillctl.eval.factory import list_judges
from skillctl.eval.loader import EvalLoadError
from skillctl.messaging import FrameworkError, emit, info
from skillctl.project_config import load_project_config
from skillctl.run.factory import list_runtimes
from skillctl.skill_yaml import SkillYamlError, load_skill_yaml
from skillctl.strictness import Strictness


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "eval",
        help="Run the behavioral eval corpus against the skill",
        description=(
            "Evaluate skill behavior against the JSON corpus under ./evals. "
            "Each `*.json` is one suite (name = filename stem). Suite shape: "
            '{"skill_name": "...", "evals": [{"id", "prompt", '
            '"expected_output", "files", "assertions"}, ...]}.'
        ),
    )
    p.add_argument(
        "skill_dir",
        nargs="?",
        default=".",
        help="Path to the skill directory (default: current directory)",
    )
    p.add_argument(
        "--mode",
        default="fast",
        choices=[m.value for m in EvalMode],
        help=(
            "Eval mode (default: fast). "
            "smoke = one case per suite; fast = every case; "
            "full = fast + regression compare (Phase 3)."
        ),
    )
    p.add_argument(
        "--suite",
        default=None,
        metavar="NAME",
        help="Restrict to one suite by name (e.g. `behavior`, `triggers`).",
    )
    p.add_argument(
        "--case",
        default=None,
        metavar="ID",
        help="Restrict to one case id (matches stringified case id).",
    )
    p.add_argument(
        "--runtime",
        default="mock",
        choices=list_runtimes(),
        help="AgentRuntime adapter (default: mock — no API key required).",
    )
    p.add_argument(
        "--judge",
        default="heuristic",
        choices=list_judges(),
        help=(
            "Judge implementation (default: heuristic — deterministic, no API key). "
            "Phase 4 adds `llm` once the Claude Agent SDK adapter ships."
        ),
    )
    p.add_argument(
        "--strictness",
        default=None,
        choices=[s.value for s in Strictness],
        help="Override strictness (default: read from skill.yaml, then project config).",
    )
    p.add_argument(
        "--output",
        default="text",
        choices=["text", "json", "silent"],
        help="Output format (default: text)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()

    if not skill_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"skill directory not found: {skill_dir}",
                fix="Pass an existing directory, or `cd` into the skill first.",
            )
        )
        return 2

    if not (skill_dir / "SKILL.md").exists():
        emit(
            FrameworkError(
                summary=f"SKILL.md not found at {skill_dir / 'SKILL.md'}",
                fix="Run `bbsctl new <name>` to scaffold a skill, or `cd` into one first.",
            )
        )
        return 2

    evals_dir = skill_dir / "evals"
    if not evals_dir.is_dir():
        emit(
            FrameworkError(
                summary=f"no evals/ directory found in {skill_dir}",
                fix=(
                    f"Create `{evals_dir}` with one or more `*.json` suite files. "
                    "See docs/evaluation.md for the format, or start from "
                    "reference-plugins/hello-skill/evals/behavior.json."
                ),
                docs="../docs/evaluation.md",
            )
        )
        return 2

    strictness = _resolve_strictness(skill_dir, args.strictness)
    mode = EvalMode(args.mode)

    runner = EvalRunner(
        skill_dir,
        strictness,
        mode=mode,
        runtime_name=args.runtime,
        judge_name=args.judge,
        suite_filter=args.suite,
        case_filter=args.case,
    )

    try:
        report = runner.run()
    except EvalLoadError as exc:
        emit(exc.framework_error)
        return 2
    except AgentSkillsValidationError as exc:
        emit(
            FrameworkError(
                summary=f"SKILL.md is invalid: {exc.message}",
                detail=f"agentskills.io rule violation (code={exc.code})",
                fix=exc.fix,
                docs="https://agentskills.io/specification",
            )
        )
        return 2

    if not report.suites:
        info("eval: no suites matched the filters. Nothing to do.")
        return 0

    if args.output != "silent":
        _print_report(report, fmt=args.output)

    return 0 if report.passed else 1


def _resolve_strictness(skill_dir: Path, override: str | None) -> Strictness:
    """Resolution order: CLI override > skill.yaml > [tool.bulbasaur] > LOCAL."""
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


def _print_report(report: EvalReport, *, fmt: str) -> None:
    if fmt == "json":
        sys.stdout.write(json.dumps(_report_to_dict(report), indent=2) + "\n")
        return

    # Text output.
    status = "PASSED" if report.passed else "FAILED"
    info(
        f"eval [{report.mode.value}] @ {report.strictness.value}: {status}  "
        f"(runtime={report.runtime_name}, judge={report.judge_name})"
    )
    info(f"  skill: {report.skill_dir}")
    info(
        f"  score: {report.score:.2f}  "
        f"({report.passed_cases}/{report.total_cases} case(s) passing)"
    )
    info("")

    for suite in report.suites:
        s_status = "PASS" if suite.passed else "FAIL"
        info(
            f"  suite `{suite.suite_name}`: {s_status}  "
            f"score={suite.score:.2f}  ({suite.passed_count}/{suite.total_count})"
        )
        for case in suite.cases:
            icon = "✓" if case.passed else "✗"
            info(
                f"    {icon} case id={case.case_id}  "
                f"score={case.score:.2f}  ({case.duration_ms}ms)"
            )
            if case.runtime_error:
                info(f"      runtime error: {case.runtime_error}")
            for a in case.assertions:
                a_icon = "·" if a.passed else "✗"
                info(f"      {a_icon} {a.assertion}")
                if not a.passed and a.reason:
                    info(f"          ({a.reason})")
        info("")


def _report_to_dict(report: EvalReport) -> dict:
    return {
        "passed": report.passed,
        "mode": report.mode.value,
        "strictness": report.strictness.value,
        "runtime": report.runtime_name,
        "judge": report.judge_name,
        "skill_dir": str(report.skill_dir),
        "score": report.score,
        "passed_cases": report.passed_cases,
        "total_cases": report.total_cases,
        "suites": [
            {
                "name": s.suite_name,
                "skill_name": s.skill_name,
                "passed": s.passed,
                "score": s.score,
                "passed_count": s.passed_count,
                "total_count": s.total_count,
                "cases": [
                    {
                        "id": c.case_id,
                        "prompt": c.prompt,
                        "expected_output": c.expected_output,
                        "actual_output": c.actual_output,
                        "passed": c.passed,
                        "score": c.score,
                        "duration_ms": c.duration_ms,
                        "runtime_error": c.runtime_error,
                        "assertions": [
                            {
                                "assertion": a.assertion,
                                "passed": a.passed,
                                "reason": a.reason,
                            }
                            for a in c.assertions
                        ],
                    }
                    for c in s.cases
                ],
            }
            for s in report.suites
        ],
    }


__all__ = ["register", "run"]
