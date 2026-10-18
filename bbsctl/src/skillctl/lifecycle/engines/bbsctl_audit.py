"""Fallback scan engine using existing `bbsctl audit`."""

from __future__ import annotations

import json

from skillctl import __version__
from skillctl.audit.runner import AuditRunner
from skillctl.lifecycle.engines.base import StageContext
from skillctl.lifecycle.pipeline import Stage
from skillctl.lifecycle.result import EngineInfo, Finding, StageResult, StageStatus


class BbsctlAuditEngine:
    name = "bbsctl-audit"

    def available(self) -> bool:
        return True

    def version(self) -> str:
        return __version__

    def install_fix(self) -> str:
        return "bbsctl-audit is built-in — no install needed."

    def run(self, ctx: StageContext) -> StageResult:
        runner = AuditRunner(ctx.skill_dir)
        report = runner.run()

        findings = [
            Finding(
                severity=f.severity.name.lower(),
                message=f.title,
                rule_id=f.check_name if hasattr(f, "check_name") else "",
                location="",
            )
            for f in report.all_findings
            if f.severity.value >= 2  # WARN+
        ]
        # Finding may not have check_name — rebuild from check_results
        findings = []
        for cr in report.check_results:
            for f in cr.findings:
                if f.severity.value < 2:
                    continue
                findings.append(
                    Finding(
                        severity=f.severity.name.lower(),
                        message=f.title + (f": {f.detail}" if f.detail else ""),
                        rule_id=cr.check_name,
                    )
                )

        out_dir = ctx.skill_dir / "dist"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Emit a minimal SARIF-like JSON so evidence layout stays uniform.
        sarif = {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {"driver": {"name": "bbsctl-audit", "version": __version__}},
                    "results": [
                        {
                            "ruleId": f.rule_id,
                            "level": f.severity,
                            "message": {"text": f.message},
                        }
                        for f in findings
                    ],
                }
            ],
        }
        sarif_path = out_dir / "scan.sarif"
        sarif_path.write_text(json.dumps(sarif, indent=2), encoding="utf-8")

        # FAIL severity (4) fails the stage; RISK (3) fails at regulated via findings count
        failed = report.worst_severity.value >= 4
        return StageResult(
            stage=Stage.SCAN.value,
            status=StageStatus.FAILED if failed else StageStatus.PASSED,
            findings=findings,
            artifacts={"scan.sarif": str(sarif_path)},
            engine=EngineInfo(
                name=self.name, version=self.version(), revision=self.version()
            ),
            detail=f"verdict={report.verdict}",
        )


__all__ = ["BbsctlAuditEngine"]
