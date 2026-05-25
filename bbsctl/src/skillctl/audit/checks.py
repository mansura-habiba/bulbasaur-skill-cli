"""Individual audit checks for trust evaluation of a downloaded skill.

Each check inspects one aspect of the skill and returns findings as
(severity, title, detail) tuples. Severities:

    PASS    — this aspect looks good
    INFO    — neutral observation
    WARN    — potential concern, review recommended
    RISK    — significant trust concern, action recommended
    FAIL    — trust-blocking issue
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from ruamel.yaml import YAML


class Severity(IntEnum):
    PASS = 0
    INFO = 1
    WARN = 2
    RISK = 3
    FAIL = 4


@dataclass
class Finding:
    severity: Severity
    title: str
    detail: str = ""
    recommendation: str = ""


@dataclass
class CheckResult:
    check_name: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def worst_severity(self) -> Severity:
        if not self.findings:
            return Severity.PASS
        return max(f.severity for f in self.findings)


def check_spec_completeness(skill_dir: Path) -> CheckResult:
    """Check how completely the SKILL.md frontmatter is filled in."""
    result = CheckResult(check_name="spec-completeness")
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        result.findings.append(Finding(
            Severity.FAIL, "SKILL.md missing",
            "No SKILL.md found — this is not a valid skill.",
            "Do not trust. A valid skill must have a SKILL.md file.",
        ))
        return result

    fm = _read_frontmatter(skill_md)
    if fm is None:
        result.findings.append(Finding(
            Severity.FAIL, "Frontmatter unparseable",
            "Could not parse YAML frontmatter from SKILL.md.",
            "Do not trust. The skill manifest is malformed.",
        ))
        return result

    name = fm.get("name", "")
    desc = fm.get("description", "")

    if not name:
        result.findings.append(Finding(
            Severity.FAIL, "name field missing",
            recommendation="Required by agentskills.io spec.",
        ))
    else:
        if name != skill_dir.name:
            result.findings.append(Finding(
                Severity.WARN,
                "name does not match directory",
                f"name='{name}' but directory='{skill_dir.name}'",
                "Spec requires name to match parent directory.",
            ))
        else:
            result.findings.append(Finding(
                Severity.PASS, "name matches directory",
            ))

    if not desc:
        result.findings.append(Finding(
            Severity.FAIL, "description field missing",
            recommendation="Required by agentskills.io spec.",
        ))
    elif "[" in desc and "]" in desc:
        result.findings.append(Finding(
            Severity.WARN,
            "description contains placeholder text",
            f"'{desc[:80]}...'",
            "Author has not filled in the description contract.",
        ))
    else:
        result.findings.append(Finding(
            Severity.PASS,
            "description present",
            f"{len(desc)} chars",
        ))

    if fm.get("license"):
        result.findings.append(Finding(
            Severity.PASS, "license declared",
            str(fm["license"]),
        ))
    else:
        result.findings.append(Finding(
            Severity.INFO, "no license declared",
            recommendation="Consider requesting license info from the author.",
        ))

    if fm.get("metadata"):
        meta = fm["metadata"]
        if isinstance(meta, dict) and meta.get("author"):
            result.findings.append(Finding(
                Severity.PASS, "author declared",
                str(meta["author"]),
            ))
        else:
            result.findings.append(Finding(
                Severity.INFO, "no author in metadata",
            ))
    else:
        result.findings.append(Finding(
            Severity.INFO, "no metadata declared",
        ))

    return result


def check_body_sections(skill_dir: Path) -> CheckResult:
    """Check whether the body has recommended sections."""
    result = CheckResult(check_name="body-sections")
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return result

    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return result

    body = _extract_body(text)
    headings = re.findall(r"^##\s+(.+)$", body, re.MULTILINE)
    heading_lower = [h.strip().lower() for h in headings]

    for section, sev_if_missing in [
        ("instructions", Severity.WARN),
        ("guardrails", Severity.RISK),
        ("when to use this skill", Severity.WARN),
        ("examples", Severity.INFO),
        ("edge cases", Severity.INFO),
    ]:
        if any(section in h for h in heading_lower):
            result.findings.append(Finding(
                Severity.PASS,
                f"'{section}' section present",
            ))
        else:
            result.findings.append(Finding(
                sev_if_missing,
                f"'{section}' section missing",
                recommendation=_section_recommendation(section),
            ))

    return result


def check_guardrails_quality(skill_dir: Path) -> CheckResult:
    """If a Guardrails section exists, check whether it has substance."""
    result = CheckResult(check_name="guardrails-quality")
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return result

    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return result

    body = _extract_body(text)
    guardrails = _extract_section(body, "guardrails")

    if guardrails is None:
        result.findings.append(Finding(
            Severity.RISK,
            "No guardrails defined",
            "The skill does not declare any safety boundaries.",
            "Ask the author: what must this skill never do? "
            "What input must it reject?",
        ))
        return result

    lines = [
        ln.strip() for ln in guardrails.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]

    if len(lines) < 2:
        result.findings.append(Finding(
            Severity.WARN,
            "Guardrails section is thin",
            f"Only {len(lines)} non-empty line(s).",
            "A meaningful guardrails section should cover: "
            "what to never do, what to reject, fallback behaviour.",
        ))
    else:
        has_never = any("never" in ln.lower() or "must not" in ln.lower() for ln in lines)
        has_reject = any("reject" in ln.lower() or "refuse" in ln.lower() for ln in lines)
        has_fallback = any("fallback" in ln.lower() or "fail" in ln.lower() for ln in lines)

        if has_never or has_reject or has_fallback:
            result.findings.append(Finding(
                Severity.PASS,
                "Guardrails section has actionable constraints",
                f"{len(lines)} line(s) with safety-relevant keywords",
            ))
        else:
            result.findings.append(Finding(
                Severity.WARN,
                "Guardrails section lacks safety keywords",
                "No 'never', 'must not', 'reject', 'refuse', 'fallback' found.",
                "Review whether the guardrails are concrete enough.",
            ))

    placeholder_markers = ["[", "TODO", "FIXME", "placeholder"]
    if any(m.lower() in guardrails.lower() for m in placeholder_markers):
        result.findings.append(Finding(
            Severity.WARN,
            "Guardrails contain placeholder text",
            recommendation="Author has not filled in the guardrails contract.",
        ))

    return result


def check_scripts(skill_dir: Path) -> CheckResult:
    """Check if the skill includes executable scripts and flag concerns."""
    result = CheckResult(check_name="scripts")
    scripts_dir = skill_dir / "scripts"

    if not scripts_dir.exists() or not scripts_dir.is_dir():
        result.findings.append(Finding(
            Severity.PASS, "No scripts/ directory",
            "This skill does not include executable code.",
        ))
        return result

    scripts = [
        s for s in scripts_dir.rglob("*")
        if s.is_file() and s.name != ".gitkeep"
    ]

    if not scripts:
        result.findings.append(Finding(
            Severity.PASS, "scripts/ directory is empty",
        ))
        return result

    result.findings.append(Finding(
        Severity.WARN,
        f"Skill includes {len(scripts)} script(s)",
        ", ".join(s.name for s in scripts[:10]),
        "Review each script before trusting this skill. "
        "Scripts execute on your machine with your permissions.",
    ))

    for script in scripts:
        try:
            content = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        dangerous_patterns = [
            (r"curl\s.*\|\s*(bash|sh)", "pipes remote content to shell"),
            (r"wget\s.*&&\s*(bash|sh)", "downloads and executes"),
            (r"eval\s*\(", "uses eval()"),
            (r"exec\s*\(", "uses exec()"),
            (r"os\.system\s*\(", "uses os.system()"),
            (r"subprocess.*shell\s*=\s*True", "uses shell=True"),
            (r"rm\s+-rf\s+/", "recursive delete from root"),
            (r"chmod\s+777", "sets world-writable permissions"),
        ]

        for pattern, desc in dangerous_patterns:
            if re.search(pattern, content):
                result.findings.append(Finding(
                    Severity.RISK,
                    f"Script '{script.name}' {desc}",
                    f"Pattern: {pattern}",
                    f"Manually review {script.relative_to(skill_dir)} "
                    "before trusting this skill.",
                ))

    return result


def check_allowed_tools(skill_dir: Path) -> CheckResult:
    """Check what tools the skill requests permission to use."""
    result = CheckResult(check_name="allowed-tools")
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        return result

    fm = _read_frontmatter(skill_md)
    if fm is None:
        return result

    tools_str = fm.get("allowed-tools", "")
    if not tools_str:
        result.findings.append(Finding(
            Severity.INFO,
            "No allowed-tools declared",
            "The skill does not request pre-approved tool access.",
        ))
        return result

    tools = tools_str.strip().split()
    result.findings.append(Finding(
        Severity.INFO,
        f"Requests {len(tools)} tool permission(s)",
        ", ".join(tools),
    ))

    broad_patterns = [
        ("Bash(*)", "unrestricted shell access"),
        ("Bash(*)(*)", "unrestricted shell access"),
        ("*", "wildcard — all tools"),
    ]
    for tool in tools:
        for pattern, desc in broad_patterns:
            if tool == pattern:
                result.findings.append(Finding(
                    Severity.RISK,
                    f"Broad tool permission: '{tool}'",
                    desc,
                    "Prefer scoped permissions like 'Bash(git:*)' "
                    "instead of unrestricted access.",
                ))

    return result


def check_skill_yaml(skill_dir: Path) -> CheckResult:
    """Check the enterprise overlay for trust signals."""
    result = CheckResult(check_name="enterprise-overlay")
    skill_yaml = skill_dir / "skill.yaml"

    if not skill_yaml.exists():
        result.findings.append(Finding(
            Severity.INFO,
            "No skill.yaml (local strictness)",
            "No enterprise overlay — this skill has no ownership, "
            "signing, or strictness declaration.",
            "For production use, request that the author publishes "
            "at team+ strictness with ownership declared.",
        ))
        return result

    try:
        yaml = YAML(typ="safe")
        data = yaml.load(skill_yaml.read_text(encoding="utf-8"))
    except Exception:
        result.findings.append(Finding(
            Severity.WARN,
            "skill.yaml is unparseable",
            recommendation="The enterprise overlay is malformed.",
        ))
        return result

    if not isinstance(data, dict):
        return result

    strictness = data.get("strictness", "local")
    result.findings.append(Finding(
        Severity.PASS if strictness != "local" else Severity.INFO,
        f"Strictness: {strictness}",
    ))

    ownership = data.get("ownership")
    if ownership and isinstance(ownership, dict):
        team = ownership.get("team", "")
        contact = ownership.get("contact", "")
        result.findings.append(Finding(
            Severity.PASS,
            "Ownership declared",
            f"team={team}, contact={contact}",
        ))
    else:
        result.findings.append(Finding(
            Severity.WARN,
            "No ownership declared",
            recommendation="No accountable team or contact. "
            "For production skills, require ownership.",
        ))

    return result


# ── helpers ──────────────────────────────────────────────────────────────────

def _read_frontmatter(skill_md: Path) -> dict | None:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == "---"),
        None,
    )
    if closing is None:
        return None

    fm_text = "\n".join(lines[1:closing])
    yaml = YAML(typ="safe")
    try:
        parsed = yaml.load(io.StringIO(fm_text)) or {}
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_body(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == "---"),
        None,
    )
    if closing is None:
        return text
    return "\n".join(lines[closing + 1:])


def _extract_section(body: str, heading: str) -> str | None:
    """Extract content under a ## heading until the next ## or end."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, body, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None

    start = match.end()
    next_heading = re.search(r"^##\s+", body[start:], re.MULTILINE)
    if next_heading:
        return body[start:start + next_heading.start()]
    return body[start:]


def _section_recommendation(section: str) -> str:
    recs = {
        "instructions": (
            "Without instructions, the agent has no guidance on what to do."
        ),
        "guardrails": (
            "Without guardrails, there are no declared safety boundaries. "
            "Ask the author: what must this skill never do?"
        ),
        "when to use this skill": (
            "Without activation cues, the agent may activate at the wrong time."
        ),
        "examples": (
            "Examples help verify the skill does what you expect."
        ),
        "edge cases": (
            "Edge cases help understand failure modes."
        ),
    }
    return recs.get(section, "")


ALL_CHECKS = [
    check_spec_completeness,
    check_body_sections,
    check_guardrails_quality,
    check_scripts,
    check_allowed_tools,
    check_skill_yaml,
]

__all__ = [
    "ALL_CHECKS",
    "CheckResult",
    "Finding",
    "Severity",
]
