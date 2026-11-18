"""Transport-neutral Bulbasaur service: no FastMCP, CLI or HTTP imports.

Uses the existing skillctl compiler in an ephemeral workspace. Only structural
and static checks execute; no LLM, external scanner, publisher, or installer.
"""
from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any

from skillctl.compile.factory import build_pipeline
from skillctl.compile.pipeline import CompileContext
from skillctl.compile.reporter import NullReporter
from skillctl.strictness import Strictness

from .behavior import (
    EvaluationConfigurationError, load_operator_policy,
    normalize_request, run_behavioral_evaluation,
)

SCHEMA_VERSION = "bulbasaur.assessment/v1"
MAX_SKILL_BYTES = 128 * 1024
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _finding(code: str, message: str, severity: str = "error") -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity}


def _error_result(digest: str, findings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "artifact": {"media_type": "text/markdown", "sha256": digest},
        "assessment": {"profile": "local", "mode": "static", "checks_run": 0},
        "findings": findings,
        "behavioral_evaluation": "not_run",
        "catalog_approval": "not_applicable",
    }


class SkillAssessmentService:
    """Library API for bounded, untrusted SKILL.md structural assessment."""

    def assess(self, skill_name: str, skill_md: str, *, profile: str = "local",
               evaluation: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(skill_name, str) or not isinstance(skill_md, str):
            return _error_result("", [_finding("invalid_input", "Expected string inputs")])
        raw = skill_md.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) > MAX_SKILL_BYTES:
            return _error_result(digest, [_finding("size_limit", "SKILL.md exceeds 128 KiB")])
        if len(skill_name) > 64 or not _NAME.fullmatch(skill_name):
            return _error_result(digest, [_finding("invalid_name", "Expected a lowercase kebab-case skill name")])
        try:
            strictness = Strictness(profile)
        except ValueError:
            return _error_result(digest, [_finding("invalid_profile", "Unknown strictness profile")])
        try:
            selected_eval = normalize_request(evaluation, policy=load_operator_policy())
        except (EvaluationConfigurationError, OSError, ValueError):
            return _error_result(digest, [_finding(
                "evaluation_configuration", "Evaluation request or operator policy is invalid"
            )])
        # No caller-controlled directory; compiler artifacts remain temporary.
        with tempfile.TemporaryDirectory(prefix="bulbasaur-assessment-") as root:
            directory = Path(root) / skill_name
            directory.mkdir()
            (directory / "SKILL.md").write_bytes(raw)
            context = CompileContext(skill_dir=directory, strictness=strictness, reporter=NullReporter())
            result = build_pipeline(strictness).run(context)
            findings = []
            for step in result.step_results:
                for error in step.errors:
                    findings.append(_finding(step.step_name, "Validation failed in " + step.step_name))
                for warning in step.warnings:
                    findings.append(_finding(step.step_name, "Validation warning in " + step.step_name, "warning"))
            response = {
                "schema_version": SCHEMA_VERSION,
                "status": "passed" if result.success else "failed",
                "artifact": {"media_type": "text/markdown", "sha256": digest},
                "assessment": {
                    "profile": profile,
                    "mode": "static",
                    "checks_run": len([s for s in result.step_results if s.outcome.value != "skipped"]),
                },
                "findings": findings,
                "behavioral_evaluation": "not_run",
                "catalog_approval": "not_applicable",
            }
            if selected_eval is not None and result.success:
                response["schema_version"] = "bulbasaur.assessment/v2"
                try:
                    evidence = run_behavioral_evaluation(directory, skill_name, selected_eval)
                    response["behavioral_evaluation"] = evidence
                    if evidence["status"] != "passed":
                        response["status"] = "failed"
                except Exception:
                    # No runtime exceptions or evaluated text in API responses.
                    response["status"] = "error"
                    response["behavioral_evaluation"] = {
                        "status": "error", "runtime": selected_eval["runtime"],
                        "judge": selected_eval["judge"],
                        "mode": "deterministic_mock" if selected_eval["runtime"] == "mock" else "agent_runtime",
                        "cases_run": 0, "cases_passed": 0, "score": 0.0,
                        "corpus_sha256": "0" * 64, "case_results": [],
                    }
            return response

    def validate(self, skill_name: str, skill_md: str) -> dict[str, Any]:
        """Return original v1 validation shape, using existing parser directly.

        Intentionally does not claim the broader compiler/evaluator ran.
        """
        from skillctl.agentskills.frontmatter import parse_skill_md

        if not isinstance(skill_name, str) or not isinstance(skill_md, str):
            return {"status": "failed", "artifact_sha256": "",
                    "validator": "agentskills-frontmatter",
                    "findings": [{"code": "invalid_input", "message": "Expected string inputs"}]}
        raw = skill_md.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        base = {"artifact_sha256": digest, "validator": "agentskills-frontmatter"}
        if len(raw) > MAX_SKILL_BYTES:
            return {**base, "status": "failed", "findings": [
                {"code": "size_limit", "message": "SKILL.md exceeds 128 KiB"}]}
        if len(skill_name) > 64 or not _NAME.fullmatch(skill_name):
            return {**base, "status": "failed", "findings": [
                {"code": "invalid_name", "message": "Expected a lowercase kebab-case skill name"}]}
        try:
            with tempfile.TemporaryDirectory(prefix="bulbasaur-validate-") as root:
                directory = Path(root) / skill_name
                directory.mkdir()
                file = directory / "SKILL.md"
                file.write_bytes(raw)
                parse_skill_md(file)
        except Exception:
            return {**base, "status": "failed", "findings": [
                {"code": "invalid_skill", "message": "SKILL.md failed Agent Skills validation"}]}
        return {**base, "status": "passed", "findings": []}
