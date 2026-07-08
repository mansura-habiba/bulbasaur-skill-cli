"""Composer — orchestrates an LLM call into a complete skill scaffold."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from skillctl.agentskills import validate_name
from skillctl.agentskills.rules import AgentSkillsValidationError
from skillctl.llm import LLMBackend, LLMBackendError, build_backend
from skillctl.skill_yaml import (
    RiskLevel,
    SideEffects,
    SkillOverlay,
    write_skill_yaml,
)
from skillctl.skill_yaml import Risk as RiskBlock
from skillctl.strictness import Strictness


class SkillArchetype(str, Enum):
    """Coarse-grained category that shapes the templated permissions.yaml.

    Aligned with Mellea's five interaction patterns, but kept loose enough
    that an author can use it as a tag without forcing a strict semantics.
    """

    ANALYTICAL = "analytical"          # read-only reasoning, summarization, classification
    DEVOPS = "devops"                  # kubectl, terraform, ci/cd, deployment
    DEVELOPER_TOOLING = "dev-tooling"  # code review, refactor, test generation
    CLIENT_FACING = "client-facing"    # customer support, sales, conversational
    GENERATIVE = "generative"          # content drafting, artifact emission

    @classmethod
    def from_string(cls, value: str | None) -> SkillArchetype:
        if not value:
            return cls.ANALYTICAL
        try:
            return cls(value.lower())
        except ValueError:
            return cls.ANALYTICAL


@dataclass(frozen=True)
class AuthoringRequest:
    """What the developer asked for."""

    name: str
    intent: str
    output_dir: Path
    strictness: Strictness = Strictness.LOCAL
    archetype: SkillArchetype = SkillArchetype.ANALYTICAL
    backend_name: str | None = None
    model: str | None = None
    risk_level: RiskLevel | None = None


@dataclass
class AuthoringResult:
    """What got written."""

    skill_dir: Path
    files_written: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    used_backend: str = ""
    used_model: str = ""
    fell_back_to_skeleton: bool = False


class AuthoringError(Exception):
    """User-facing failure (name collision, bad intent, etc.)."""


# ── public entry point ──────────────────────────────────────────────────────


def author_skill(
    request: AuthoringRequest,
    *,
    backend: LLMBackend | None = None,
) -> AuthoringResult:
    """Author a complete skill scaffold from an intent description.

    `backend` is exposed for tests; production callers pass None and let the
    composer pick the configured backend through the LLM factory.
    """
    _validate_request(request)

    if backend is None:
        backend = build_backend(request.backend_name)

    notes: list[str] = []
    drafted = _draft_via_llm(request, backend, notes=notes)
    used_skeleton = drafted is None

    if drafted is None:
        drafted = _skeleton_draft(request)

    # Write everything to disk.
    out_dir = request.output_dir / request.name
    if out_dir.exists():
        raise AuthoringError(
            f"refusing to overwrite existing path: {out_dir}. "
            f"Choose a different name, or remove {out_dir} first."
        )
    out_dir.mkdir(parents=True, exist_ok=False)

    written: list[Path] = []
    written.append(_write_skill_md(out_dir, request, drafted))
    if request.strictness.includes(Strictness.TEAM):
        written.append(_write_skill_yaml(out_dir, request))
        written.append(_write_permissions_yaml(out_dir, request))
    written.append(_write_evals_behavior(out_dir, drafted))

    return AuthoringResult(
        skill_dir=out_dir,
        files_written=written,
        notes=notes,
        used_backend=backend.name,
        used_model=request.model or "",
        fell_back_to_skeleton=used_skeleton,
    )


# ── validation ──────────────────────────────────────────────────────────────


def _validate_request(req: AuthoringRequest) -> None:
    """Surface the same agentskills.io rules `bbsctl new` enforces."""
    try:
        validate_name(req.name)
    except AgentSkillsValidationError as exc:
        raise AuthoringError(
            f"invalid skill name: {exc.message}. Fix: {exc.fix}"
        ) from exc
    if not req.intent or not req.intent.strip():
        raise AuthoringError(
            "intent is required — describe what the skill should do. "
            "Pass `--intent 'restart deployments when paged'` or similar."
        )


# ── LLM draft ───────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = """\
You are a Bulbasaur skill author. Given a skill name, an intent description, \
a strictness rung, and an archetype, you produce a single JSON envelope \
containing the draft content for a new skill.

Output format — a single JSON object with these fields (no prose around it):

  {
    "description": "Replace with a sentence (<= 1024 chars) telling the agent \
when to activate this skill. Include action verbs. Mention the trigger surface.",
    "body": "Markdown body of SKILL.md (< 500 lines). Start with a `# Title` \
heading, then a `## When to reach for this skill` section with bullets, then \
`## Inputs expected`, then `## Workflow` numbered steps, then `## Outputs`. \
Use only standard Markdown.",
    "eval_cases": [
      {
        "id": 1,
        "prompt": "<a realistic user prompt that should activate this skill>",
        "expected_output": "<one sentence describing what good output looks like>",
        "assertions": [
          "<plain-english claim a judge can score against the actual output>",
          "<another assertion>"
        ]
      }
    ]
  }

Constraints:
  - The description MUST mention concrete action verbs and example triggers
    so the agent can decide whether to activate the skill.
  - 3 to 5 eval cases — at least one positive case and at least one negative
    case (a prompt the skill should NOT activate on; in that case the
    assertions describe the refusal).
  - Reply with ONE JSON object. No prose, no commentary, no Markdown fence.
"""


_USER_PROMPT_TEMPLATE = """\
Skill name: {name}
Strictness rung: {strictness}
Archetype: {archetype}
Risk level: {risk_level}

Intent (what should this skill do?):
{intent}

Now produce the JSON envelope.
"""


def _draft_via_llm(
    request: AuthoringRequest,
    backend: LLMBackend,
    *,
    notes: list[str],
) -> dict | None:
    """Run the LLM. Return None on failure so caller can fall back."""
    prompt = _USER_PROMPT_TEMPLATE.format(
        name=request.name,
        strictness=request.strictness.value,
        archetype=request.archetype.value,
        risk_level=(request.risk_level.value if request.risk_level else "unset"),
        intent=request.intent.strip(),
    )
    try:
        response = backend.complete(
            prompt=prompt,
            model=request.model,
            system=_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.2,
        )
    except LLMBackendError as exc:
        notes.append(f"llm backend error: {exc}; falling back to skeleton")
        return None

    parsed = _parse_envelope(response.text)
    if parsed is None:
        # One retry with a stricter instruction.
        try:
            retry = backend.complete(
                prompt=prompt + "\n\nIMPORTANT: reply with ONE JSON object only.",
                model=request.model,
                system=_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.0,
            )
        except LLMBackendError as exc:
            notes.append(f"llm backend error on retry: {exc}; falling back")
            return None
        parsed = _parse_envelope(retry.text)
        if parsed is None:
            notes.append("could not parse llm envelope; falling back to skeleton")
            return None

    return parsed


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_envelope(text: str) -> dict | None:
    """Best-effort JSON extraction from the model's response."""
    if not text:
        return None
    stripped = text.strip()
    candidates: list[str] = []
    if stripped.startswith("{"):
        candidates.append(stripped)
    # Greedy outer match for embedded JSON.
    m = _JSON_OBJECT_RE.search(text)
    if m and m.group(0) not in candidates:
        candidates.append(m.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "description" in data and "body" in data:
            return data
    return None


# ── skeleton fallback ──────────────────────────────────────────────────────


def _skeleton_draft(request: AuthoringRequest) -> dict:
    """Used when the LLM is unavailable or returns garbage.

    Produces a complete-but-marked draft so the developer can iterate
    manually. Better than crashing.
    """
    title = _humanize(request.name)
    return {
        "description": (
            f"[draft] Replace this sentence with a description telling the agent "
            f"when to activate {request.name}. Original intent: "
            f"{request.intent.strip()}"
        ),
        "body": (
            f"# {title}\n\n"
            f"[draft] Replace with the skill body.\n\n"
            f"## When to reach for this skill\n\n"
            f"- {request.intent.strip()}\n\n"
            f"## Inputs expected\n\n- TODO\n\n"
            f"## Workflow\n\n1. TODO\n\n"
            f"## Outputs\n\n- TODO\n"
        ),
        "eval_cases": [
            {
                "id": 1,
                "prompt": f"[draft] a realistic user prompt for {request.name}",
                "expected_output": "[draft] one sentence describing good output",
                "assertions": [
                    "[draft] assertion 1 — replace with a concrete claim",
                ],
            }
        ],
    }


def _humanize(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


# ── writers ─────────────────────────────────────────────────────────────────


def _write_skill_md(
    out_dir: Path, request: AuthoringRequest, drafted: dict
) -> Path:
    description = str(drafted.get("description") or "").strip()
    body = str(drafted.get("body") or "").strip()
    frontmatter = (
        f"---\n"
        f"name: {request.name}\n"
        f"description: {_yaml_inline_str(description)}\n"
        f"---\n\n"
    )
    path = out_dir / "SKILL.md"
    path.write_text(frontmatter + body + "\n", encoding="utf-8")
    return path


def _yaml_inline_str(value: str) -> str:
    """Inline-quote a string for YAML frontmatter.

    The frontmatter parser uses ruamel.yaml which handles most cases; we
    just need to avoid breaking out of the field when the value contains
    newlines or special leading characters.
    """
    if "\n" in value:
        # Use folded scalar.
        return ">-\n  " + value.replace("\n", "\n  ")
    if any(value.startswith(ch) for ch in ("-", "?", ":", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`")):
        return '"' + value.replace('"', '\\"') + '"'
    if ":" in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _write_skill_yaml(out_dir: Path, request: AuthoringRequest) -> Path:
    risk = (
        RiskBlock(
            level=request.risk_level,
            side_effects=_default_side_effects(request),
            requires_human_approval=request.archetype == SkillArchetype.DEVOPS,
        )
        if request.risk_level is not None
        else RiskBlock()
    )
    overlay = SkillOverlay(
        name=request.name,
        strictness=request.strictness,
        version="0.1.0",
        risk=risk,
    )
    path = out_dir / "skill.yaml"
    write_skill_yaml(path, overlay)
    return path


def _default_side_effects(request: AuthoringRequest) -> SideEffects | None:
    """Derive an opening guess at side_effects from the archetype.

    The author can tighten or loosen this later — it's a starting point so
    the validator doesn't immediately fail at org+.
    """
    return {
        SkillArchetype.ANALYTICAL: SideEffects.READ_ONLY,
        SkillArchetype.DEVOPS: SideEffects.EXTERNAL,
        SkillArchetype.DEVELOPER_TOOLING: SideEffects.REVERSIBLE,
        SkillArchetype.CLIENT_FACING: SideEffects.EXTERNAL,
        SkillArchetype.GENERATIVE: SideEffects.READ_ONLY,
    }.get(request.archetype)


def _write_permissions_yaml(
    out_dir: Path, request: AuthoringRequest
) -> Path:
    """Template a permissions.yaml shaped by the archetype.

    Reviewed and tightened later by the developer. We err on the side of
    deny-by-default so the developer is explicit about widening.
    """
    if request.archetype == SkillArchetype.DEVOPS:
        body = _devops_permissions(request)
    elif request.archetype == SkillArchetype.CLIENT_FACING:
        body = _client_facing_permissions(request)
    elif request.archetype == SkillArchetype.DEVELOPER_TOOLING:
        body = _dev_tooling_permissions(request)
    elif request.archetype == SkillArchetype.GENERATIVE:
        body = _generative_permissions(request)
    else:
        body = _analytical_permissions(request)
    path = out_dir / "permissions.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _analytical_permissions(request: AuthoringRequest) -> str:
    return f"""schema_version: bulbasaur/v1
skill: {request.name}

# Read-only analytical skill — no shell commands, no network writes.
commands:
  default: deny
  allow: []
  deny:
    - pattern: '\\b(rm -rf|chmod 777|sudo)\\b'
      reason: dangerous local-shell patterns

network:
  default: deny
  allowed_sites: []

filesystem:
  read_paths: []
  write_paths: []

env:
  allow: []
  redact:
    - '.*_TOKEN'
    - '.*_SECRET'
    - '.*_PASSWORD'
"""


def _devops_permissions(request: AuthoringRequest) -> str:
    return f"""schema_version: bulbasaur/v1
skill: {request.name}

# DevOps skill — allow read-only kubectl + diagnostic operations by default.
# Tighten the allow list to specific verbs the skill actually needs.
commands:
  default: deny
  allow:
    - pattern: '^kubectl get( [^|;&`$]+)?$'
      reason: read-only kubectl queries
    - pattern: '^kubectl describe (pod|deploy|svc) [a-z0-9-]+ -n [a-z0-9-]+( --context [a-z0-9-]+)?$'
      reason: diagnostic describe
  deny:
    - pattern: '\\bkubectl exec\\b.*(-it|--stdin|--tty)\\b'
      reason: interactive shells prohibited
    - pattern: '\\b(kubectl|oc) (delete|rm)\\b'
      reason: destructive operations require explicit approval

namespaces:
  allow: []  # populate with explicit allowlist before publish
  deny: [kube-system, kube-public, flux-system, cert-manager]

network:
  default: deny
  allowed_sites:
    - pattern: '^https://kubernetes\\.io/docs/'

env:
  allow:
    - KUBECONFIG
  redact:
    - '.*_TOKEN'
    - '.*_SECRET'
    - '.*_PASSWORD'
"""


def _client_facing_permissions(request: AuthoringRequest) -> str:
    return f"""schema_version: bulbasaur/v1
skill: {request.name}

# Client-facing skill — no shell commands, restricted network, PII redaction.
commands:
  default: deny
  allow: []

network:
  default: deny
  allowed_sites:
    - pattern: '^https://api\\.internal\\.example\\.com/'

env:
  allow: []
  redact:
    - '.*_TOKEN'
    - '.*_SECRET'
    - '.*_PASSWORD'
    - '.*_PII'
"""


def _dev_tooling_permissions(request: AuthoringRequest) -> str:
    return f"""schema_version: bulbasaur/v1
skill: {request.name}

# Developer-tooling skill — code-related operations within the project.
commands:
  default: deny
  allow:
    - pattern: '^git (status|diff|log|show)( .+)?$'
      reason: read-only git inspection
    - pattern: '^(pytest|npm test|cargo test)( .+)?$'
      reason: run tests
  deny:
    - pattern: '\\bgit (push|reset --hard|rebase)\\b'
      reason: destructive git operations

filesystem:
  read_paths: ["$PWD/**"]
  write_paths: ["$PWD/**"]

env:
  allow: [PATH, HOME]
  redact:
    - '.*_TOKEN'
    - '.*_SECRET'
"""


def _generative_permissions(request: AuthoringRequest) -> str:
    return f"""schema_version: bulbasaur/v1
skill: {request.name}

# Generative content skill — no shell, no network writes, no secret access.
commands:
  default: deny
  allow: []

network:
  default: deny
  allowed_sites: []

env:
  allow: []
  redact:
    - '.*_TOKEN'
    - '.*_SECRET'
"""


def _write_evals_behavior(out_dir: Path, drafted: dict) -> Path:
    cases = drafted.get("eval_cases") or []
    if not isinstance(cases, list):
        cases = []
    skill_name = out_dir.name
    payload = {
        "skill_name": skill_name,
        "evals": [_normalize_case(c, i) for i, c in enumerate(cases, start=1)],
    }
    evals_dir = out_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    path = evals_dir / "behavior.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _normalize_case(raw: Any, index: int) -> dict:
    if not isinstance(raw, dict):
        return {
            "id": index,
            "prompt": "",
            "expected_output": "",
            "files": [],
            "assertions": [],
        }
    return {
        "id": raw.get("id") or index,
        "prompt": str(raw.get("prompt") or ""),
        "expected_output": str(raw.get("expected_output") or ""),
        "files": list(raw.get("files") or []),
        "assertions": [str(a) for a in (raw.get("assertions") or [])],
    }


__all__ = [
    "AuthoringError",
    "AuthoringRequest",
    "AuthoringResult",
    "SkillArchetype",
    "author_skill",
]
