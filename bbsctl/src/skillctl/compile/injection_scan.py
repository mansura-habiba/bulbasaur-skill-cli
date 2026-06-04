"""SkillBodyInjectionScanStep — compile-time scan of SKILL.md body.

The `InjectionEvaluator` (eval module) tests how the *agent* responds when an
injection payload is sent to it. This step tests whether the *skill author*
has accidentally (or maliciously) embedded injection-shaped patterns in the
SKILL.md body itself — patterns that, if executed by the agent, would
override its instructions, exfil data, disable validation, or grant
broader-than-declared authority.

Severity-graded:
  team       warning per match (does not fail compile)
  org+       error per match (fails compile)

The pattern catalogue is conservative: high-precision regex over phrases
that have no legitimate place in a SKILL.md body. False positives are
preferable to false negatives at `org+` because the author can either
rephrase the body or document the false positive in `permissions.yaml`.

Categories mirror the runtime InjectionEvaluator so the two layers share
a taxonomy:

  instruction_override      "ignore previous instructions", "disregard…"
  system_prompt_extraction  "reveal your system prompt", "print your context"
  validation_disable        "skip validation", "bypass policy", "disable hooks"
  exfiltration              "send to <external URL>", "post to attacker"
  tool_invocation_hijack    "use all tools", "invoke without permission"
  secret_access             "read ~/.ssh/", "cat .env", "print AWS_SECRET"
  authority_grant           "you are now an unrestricted assistant", role-play override
  url_in_body               any http(s):// in the body (warning only — informational)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from skillctl.messaging import FrameworkError
from skillctl.strictness import Strictness

from .pipeline import CompileContext, CompileStep, StepOutcome, StepResult


@dataclass(frozen=True)
class InjectionPattern:
    """One pattern in the body-scan catalogue."""

    category: str
    pattern: str
    reason: str
    case_insensitive: bool = True


# The pattern catalogue. Conservative — every entry has been chosen because
# it has no legitimate use in a SKILL.md body. URL extraction is handled
# separately because it's informational (URLs are often legitimate references).
_PATTERNS: tuple[InjectionPattern, ...] = (
    # ── instruction_override ────────────────────────────────────────────
    InjectionPattern(
        category="instruction_override",
        pattern=r"\bignore\s+(all\s+|the\s+)?previous\s+instructions?\b",
        reason="phrase used in injection attacks to override system prompts",
    ),
    InjectionPattern(
        category="instruction_override",
        pattern=r"\bdisregard\s+(all\s+|the\s+)?(previous|prior|system|user)\s+instructions?\b",
        reason="phrase used to override prior instructions",
    ),
    InjectionPattern(
        category="instruction_override",
        pattern=r"\boverride\s+(the\s+)?system\s+(prompt|instructions?)\b",
        reason="explicit system-prompt override",
    ),
    InjectionPattern(
        category="instruction_override",
        pattern=r"\bdo\s+not\s+tell\s+the\s+user\b",
        reason="explicit instruction to hide actions from the user",
    ),
    # ── system_prompt_extraction ────────────────────────────────────────
    InjectionPattern(
        category="system_prompt_extraction",
        pattern=r"\breveal\s+(your|the)\s+system\s+prompt\b",
        reason="system-prompt extraction attempt",
    ),
    InjectionPattern(
        category="system_prompt_extraction",
        pattern=r"\bprint\s+(your|the)\s+(context|instructions?|system\s+prompt)\b",
        reason="context-extraction attempt",
    ),
    # ── validation_disable ──────────────────────────────────────────────
    InjectionPattern(
        category="validation_disable",
        pattern=r"\b(skip|bypass|disable)\s+(validation|the\s+validator|policy|policies|safety\s+checks?)\b",
        reason="attempts to disable framework gates",
    ),
    InjectionPattern(
        category="validation_disable",
        pattern=r"\b(disable|bypass)\s+(the\s+)?(hooks?|guardrails?|firewall)\b",
        reason="attempts to disable runtime hooks",
    ),
    # ── exfiltration ────────────────────────────────────────────────────
    InjectionPattern(
        category="exfiltration",
        pattern=r"\bexfiltrate\b",
        reason="literal exfiltration request",
    ),
    InjectionPattern(
        category="exfiltration",
        pattern=r"\bsend\s+(the\s+)?(output|results?|data|file|files)\s+to\s+http",
        reason="external POST instruction",
    ),
    InjectionPattern(
        category="exfiltration",
        pattern=r"\bpost\s+(the\s+)?(output|results?|data|file)\s+to\s+https?://",
        reason="external POST instruction",
    ),
    InjectionPattern(
        category="exfiltration",
        pattern=r"\bupload\s+(the\s+)?(extracted|output|results?|data)\s+to\b",
        reason="external upload instruction",
    ),
    # ── tool_invocation_hijack ──────────────────────────────────────────
    InjectionPattern(
        category="tool_invocation_hijack",
        pattern=r"\buse\s+all\s+(available\s+)?tools?\b",
        reason="broad tool grant — manifest must enumerate tools explicitly",
    ),
    InjectionPattern(
        category="tool_invocation_hijack",
        pattern=r"\binvoke\s+(any|every|all)\s+tools?\s+without\s+(asking|permission|approval)",
        reason="instructions to bypass tool approval",
    ),
    # ── secret_access ───────────────────────────────────────────────────
    InjectionPattern(
        category="secret_access",
        pattern=r"\b(read|cat|print|emit)\s+(~/\.ssh/|/etc/passwd|/etc/shadow|.*\.env\b)",
        reason="reads sensitive system files",
    ),
    InjectionPattern(
        category="secret_access",
        pattern=r"\b(reveal|print|emit|leak)\s+([A-Z_]+_)?(SECRET|TOKEN|PASSWORD|API[_-]?KEY|PRIVATE[_-]?KEY)\b",
        reason="references named secret env vars",
    ),
    # ── authority_grant ─────────────────────────────────────────────────
    InjectionPattern(
        category="authority_grant",
        pattern=r"\byou\s+are\s+now\s+(an?\s+)?(unrestricted|jailbroken|free|root|admin)\b",
        reason="role-play override pattern",
    ),
    InjectionPattern(
        category="authority_grant",
        pattern=r"\bact\s+as\s+(if\s+you\s+are\s+)?(an?\s+)?(unrestricted|jailbroken|root|admin)\b",
        reason="role-play override pattern",
    ),
    InjectionPattern(
        category="authority_grant",
        pattern=r"\bDAN\s+mode\b",
        case_insensitive=False,
        reason="DAN (Do Anything Now) jailbreak reference",
    ),
)

# URL extraction — informational, not blocking. Matches any http(s) URL.
_URL_REGEX = re.compile(r"https?://[^\s)>\]\"'`]+", re.IGNORECASE)


@dataclass(frozen=True)
class _Hit:
    """One match against the pattern catalogue."""

    line_number: int          # 1-based line number in the original SKILL.md
    category: str
    matched_text: str
    reason: str
    pattern: str


class SkillBodyInjectionScanStep(CompileStep):
    """Scan SKILL.md body for injection-shaped patterns.

    Runs after ParseFrontmatterStep so the parsed body is available on the
    context. Skips silently if the parse failed.

    Severity grading:
      strictness LOCAL  - all matches are warnings (informational)
      strictness TEAM   - all matches are warnings
      strictness ORG+   - matches are errors (block compile)
    """

    name = "skill-body-injection-scan"

    def applies_to(self, context: CompileContext) -> bool:
        return context.frontmatter is not None

    def run(self, context: CompileContext) -> StepResult:
        started = time.monotonic()
        body = context.frontmatter.body or ""
        if not body.strip():
            return StepResult(
                step_name=self.name,
                outcome=StepOutcome.OK,
                duration_ms=int((time.monotonic() - started) * 1000),
                payload={"hits": 0, "categories": []},
            )

        # Pre-compile each pattern. Frozen catalogue, hot per-compile.
        hits = _scan_body(body)

        is_org_or_above = context.strictness.includes(Strictness.ORG)
        errors: list[FrameworkError] = []
        warnings: list[FrameworkError] = []
        categories_seen: set[str] = set()

        for hit in hits:
            categories_seen.add(hit.category)
            err = FrameworkError(
                summary=(
                    f"SKILL.md body matches `{hit.category}` injection pattern "
                    f"at line {hit.line_number}"
                ),
                detail=(
                    f"matched text: {hit.matched_text!r}; reason: {hit.reason}"
                ),
                fix=(
                    "Rephrase the body to avoid this pattern. If this is a "
                    "legitimate quotation (e.g. documenting an attack the skill "
                    "defends against), wrap the line in a markdown blockquote "
                    "(`> …`) so the scanner treats it as illustrative content "
                    "rather than instructional text."
                ),
            )
            if is_org_or_above:
                errors.append(err)
            else:
                warnings.append(err)

        outcome = (
            StepOutcome.FAILED
            if errors
            else (StepOutcome.WARNED if warnings else StepOutcome.OK)
        )

        return StepResult(
            step_name=self.name,
            outcome=outcome,
            duration_ms=int((time.monotonic() - started) * 1000),
            errors=errors,
            warnings=warnings,
            payload={
                "hits": len(hits),
                "categories": sorted(categories_seen),
                "urls": _extract_urls(body),
            },
        )


def _scan_body(body: str) -> list[_Hit]:
    """Walk every line of the body, return matches against the catalogue.

    Skips lines that are markdown blockquotes (`>` at line start) — those are
    illustrative and the author has flagged them as quotation, not instruction.
    Also skips fenced code blocks (between triple-backtick fences) for the same
    reason: code examples often include adversarial inputs deliberately.
    """
    hits: list[_Hit] = []
    in_fence = False
    fence_marker = "```"

    for i, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line
        stripped = line.lstrip()

        # Track code fence state.
        if stripped.startswith(fence_marker):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Skip blockquote lines (author-flagged illustrative content).
        if stripped.startswith(">"):
            continue

        for spec in _PATTERNS:
            flags = re.IGNORECASE if spec.case_insensitive else 0
            match = re.search(spec.pattern, line, flags)
            if match:
                hits.append(
                    _Hit(
                        line_number=i,
                        category=spec.category,
                        matched_text=match.group(0),
                        reason=spec.reason,
                        pattern=spec.pattern,
                    )
                )
    return hits


def _extract_urls(body: str) -> list[str]:
    """Pull every http(s) URL out of the body for the compile report.

    Informational — URLs are commonly legitimate references. Surface so a
    reviewer can quickly see the external surface a SKILL.md declares.
    Trailing sentence punctuation is stripped from each match.
    """
    raw = _URL_REGEX.findall(body)
    cleaned = [m.rstrip(".,;:!?") for m in raw]
    return sorted(set(cleaned))


__all__ = ["InjectionPattern", "SkillBodyInjectionScanStep"]
