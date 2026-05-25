"""AuditRunner — orchestrate all trust checks and produce a report."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .checks import ALL_CHECKS, CheckResult, Finding, Severity

_VERDICT_LABELS = {
    Severity.PASS: "TRUSTED",
    Severity.INFO: "TRUSTED",
    Severity.WARN: "REVIEW",
    Severity.RISK: "DO NOT TRUST (without review)",
    Severity.FAIL: "DO NOT TRUST",
}

_SEVERITY_SYMBOLS = {
    Severity.PASS: "✓",
    Severity.INFO: "i",
    Severity.WARN: "⚠",
    Severity.RISK: "✗",
    Severity.FAIL: "✗",
}


@dataclass
class AuditReport:
    skill_dir: Path
    check_results: list[CheckResult] = field(default_factory=list)

    @property
    def worst_severity(self) -> Severity:
        if not self.check_results:
            return Severity.PASS
        return max(r.worst_severity for r in self.check_results)

    @property
    def verdict(self) -> str:
        return _VERDICT_LABELS.get(self.worst_severity, "UNKNOWN")

    @property
    def all_findings(self) -> list[Finding]:
        out: list[Finding] = []
        for cr in self.check_results:
            out.extend(cr.findings)
        return out

    def format_text(self) -> str:
        lines: list[str] = []
        lines.append(f"  skill: {self.skill_dir}")
        lines.append("")

        for cr in self.check_results:
            sym = _SEVERITY_SYMBOLS.get(cr.worst_severity, "?")
            lines.append(f"  {sym} {cr.check_name}")
            for f in cr.findings:
                fsym = _SEVERITY_SYMBOLS.get(f.severity, "?")
                label = f.severity.name
                lines.append(f"    {fsym} [{label}] {f.title}")
                if f.detail:
                    lines.append(f"        {f.detail}")
                if f.recommendation:
                    lines.append(
                        f"        → {f.recommendation}"
                    )
            lines.append("")

        return "\n".join(lines)

    def format_json(self) -> str:
        data = {
            "skill_dir": str(self.skill_dir),
            "verdict": self.verdict,
            "worst_severity": self.worst_severity.name,
            "checks": [],
        }
        for cr in self.check_results:
            check_data = {
                "check": cr.check_name,
                "worst_severity": cr.worst_severity.name,
                "findings": [],
            }
            for f in cr.findings:
                check_data["findings"].append({
                    "severity": f.severity.name,
                    "title": f.title,
                    "detail": f.detail,
                    "recommendation": f.recommendation,
                })
            data["checks"].append(check_data)
        return json.dumps(data, indent=2)


class AuditRunner:
    """Run all trust audit checks on a skill directory."""

    def __init__(self, skill_dir: Path) -> None:
        self._skill_dir = skill_dir

    def run(self) -> AuditReport:
        results: list[CheckResult] = []
        for check_fn in ALL_CHECKS:
            results.append(check_fn(self._skill_dir))
        return AuditReport(
            skill_dir=self._skill_dir,
            check_results=results,
        )


__all__ = ["AuditReport", "AuditRunner"]
