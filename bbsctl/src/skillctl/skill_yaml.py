"""skill.yaml — the enterprise overlay sibling to SKILL.md.

`skill.yaml` is the Phase 2+ enterprise overlay that sits beside `SKILL.md` in
a skill directory. At `local` strictness it is optional; at `team` it is
required. It carries the fields the public agentskills.io spec does not define:
strictness, ownership ref, marketplace config, output contract, model compat,
declared policies, and **risk profile** (level + data classification + side
effects + approval requirement).

The risk profile is the content axis that pairs with the strictness ladder's
consent axis. Strictness declares how much friction the author has opted into;
risk declares what the skill is allowed to *do* once it runs.

See: framework-build-plan.md §1, ADR 0003, ADR 0007.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError
from skillctl.strictness import Strictness

_SKILL_YAML_NAME = "skill.yaml"

# Fields that MUST be present at team+ strictness.
_TEAM_REQUIRED_FIELDS = ("name", "strictness", "version")


@dataclass
class OutputContract:
    """Declared input/output shape for a skill. Optional at `team`; required at `org`+.

    `schema` is a dict conforming to JSON Schema Draft 7. At team strictness we
    only check it is a valid dict; full schema validation lands in Phase 3.
    """

    output: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class OwnershipRef:
    """Stub ownership reference embedded in skill.yaml.

    Full ownership.yaml lands at org+. At team we capture enough to warn
    when ownership is missing (the ladder warning, not a block).
    """

    team: str | None = None
    contact: str | None = None
    runbook: str | None = None


class RiskLevel(str, Enum):
    """How much damage a misuse of this skill could cause.

    Orthogonal to the strictness ladder:
      strictness = consent (how much friction the author opted into)
      risk_level = content (what the skill is allowed to *do* once it runs)

    A markdown-formatting skill at `org` strictness is `low` risk.
    A deployment-pipeline skill at `org` strictness is `critical` risk.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def from_string(cls, value: str | None) -> RiskLevel | None:
        if not value:
            return None
        try:
            return cls(str(value).lower())
        except ValueError:
            return None

    def at_least(self, other: RiskLevel) -> bool:
        order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
        return order.index(self) >= order.index(other)


class DataClassification(str, Enum):
    """The most sensitive class of data this skill may touch."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    REGULATED = "regulated"
    PII = "pii"
    PHI = "phi"

    @classmethod
    def from_string(cls, value: str | None) -> DataClassification | None:
        if not value:
            return None
        try:
            return cls(str(value).lower())
        except ValueError:
            return None


class SideEffects(str, Enum):
    """The blast radius of the skill's tool calls.

    none         — no tool calls at all (pure reasoning, summarization)
    read_only    — reads only; no writes, no external calls
    reversible   — writes that can be undone (a draft email, a kubectl patch
                   that can be rolled back, a database UPDATE inside a tx)
    external     — talks to external systems (API calls, emails sent)
    destructive  — irreversible writes (DELETE, drop table, production deploy)
    """

    NONE = "none"
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"

    @classmethod
    def from_string(cls, value: str | None) -> SideEffects | None:
        if not value:
            return None
        try:
            return cls(str(value).lower())
        except ValueError:
            return None


@dataclass(frozen=True)
class Risk:
    """Risk profile of a skill, declared in skill.yaml under `risk:`.

    All fields are optional but the policy layer will require subsets at
    higher strictness rungs. A `regulated` skill must declare every field.
    """

    level: RiskLevel | None = None
    data_classification: DataClassification | None = None
    side_effects: SideEffects | None = None
    requires_human_approval: bool = False

    @property
    def declared(self) -> bool:
        """True when at least one risk field is set (i.e. the author engaged)."""
        return (
            self.level is not None
            or self.data_classification is not None
            or self.side_effects is not None
            or self.requires_human_approval
        )

    @property
    def is_complete(self) -> bool:
        """True when every risk field is set — required at regulated strictness."""
        return (
            self.level is not None
            and self.data_classification is not None
            and self.side_effects is not None
        )


@dataclass(frozen=True)
class Provenance:
    """Skill provenance — where this skill came from and who approved it.

    Declared in skill.yaml under `provenance:`. Auto-populated by
    `bbsctl publish` from the local git state when fields are empty (the
    helper reads `git rev-parse HEAD`, `git remote get-url origin`, etc.).

    Required at `org+` strictness. The publish gate refuses to upload a
    bundle whose claimed `commit_sha` doesn't match the git state of the
    source tree it was built from — closes the "smuggled artifact" attack.
    """

    source_repo: str = ""          # e.g. "github.com/acme/skill-pdf-processing"
    commit_sha: str = ""           # 40-char hex; auto-populated from `git rev-parse HEAD`
    source_repo_branch: str = ""   # e.g. "main"; auto-populated from `git symbolic-ref`
    approved_by: str = ""          # e.g. "security-review-board" or an email
    approved_at: date | None = None  # ISO date of the approval
    build_tool: str = ""           # e.g. "bbsctl 0.1.1" — set automatically at publish time

    @property
    def declared(self) -> bool:
        """True when at least one provenance field is set."""
        return bool(
            self.source_repo
            or self.commit_sha
            or self.source_repo_branch
            or self.approved_by
            or self.approved_at
            or self.build_tool
        )

    @property
    def has_minimum(self) -> bool:
        """Org-tier minimum: source_repo + commit_sha must be set."""
        return bool(self.source_repo) and bool(self.commit_sha)

    @property
    def has_approval(self) -> bool:
        """Regulated-tier minimum: approval fields must be populated."""
        return bool(self.approved_by) and self.approved_at is not None


@dataclass
class SkillOverlay:
    """Parsed content of a skill's skill.yaml enterprise overlay.

    This is the validated in-memory representation; the raw YAML dict is not
    exposed outside this module.
    """

    # Always present after successful parse at team+.
    name: str
    strictness: Strictness
    version: str = "0.1.0"

    # Optional at team, required at org+.
    ownership: OwnershipRef | None = None
    marketplace: str | None = None

    # Optional at all levels.
    output_contract: OutputContract | None = None
    model_compatibility: list[dict[str, Any]] = field(default_factory=list)

    # Policies the skill declares it conforms to. Each entry is either a
    # catalog short-name (`hipaa-baseline`) or a path to a YAML file
    # (`./policies/internal.yaml`). Required at org+ strictness when the
    # framework's hardcoded rung defaults are not sufficient.
    policies: list[str] = field(default_factory=list)

    # Risk profile — what the skill is allowed to *do* once it runs.
    # Recommended at `team`, required at `org`, fully populated at `regulated`.
    risk: Risk = field(default_factory=Risk)

    # Provenance — where this skill came from and who approved it. Required
    # at `org+`. Auto-populated by `bbsctl publish` from the git state when
    # left empty in the source tree.
    provenance: Provenance = field(default_factory=Provenance)

    # Raw dict of any unrecognized keys — forwarded through for forward-compat.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def has_ownership(self) -> bool:
        return self.ownership is not None and bool(self.ownership.team)


class SkillYamlError(Exception):
    """Structured parse / validation error for skill.yaml.

    Carries a FrameworkError so callers can emit it directly.
    """

    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


def load_skill_yaml(skill_dir: Path) -> SkillOverlay | None:
    """Parse skill.yaml from `skill_dir`. Returns None if the file is absent.

    Raises `SkillYamlError` if the file exists but cannot be parsed or fails
    team-strictness minimum requirements.
    """
    path = skill_dir / _SKILL_YAML_NAME
    if not path.exists():
        return None

    yaml = YAML(typ="safe")
    try:
        raw = yaml.load(path)
    except Exception as exc:
        raise SkillYamlError(
            FrameworkError(
                summary="skill.yaml: YAML parse error",
                detail=str(exc),
                fix=(
                    "Fix the YAML syntax in skill.yaml. "
                    "Run `python -c 'import ruamel.yaml; "
                    "ruamel.yaml.YAML().load(open(\"skill.yaml\"))'` "
                    "locally to see the line/column."
                ),
                docs="../docs/strictness-levels.md",
            )
        ) from exc

    if not isinstance(raw, dict):
        raise SkillYamlError(
            FrameworkError(
                summary="skill.yaml: must be a YAML mapping at the top level",
                fix="The file should start with `name: <skill-name>`, not a list or scalar.",
            )
        )

    return _parse_overlay(raw, path=path)


def _parse_overlay(raw: dict[str, Any], *, path: Path) -> SkillOverlay:
    """Convert a raw YAML dict into a validated SkillOverlay."""
    known = {"name", "strictness", "version", "ownership", "marketplace",
             "output_contract", "model_compatibility", "policies", "risk",
             "provenance"}
    extra = {k: v for k, v in raw.items() if k not in known}

    name = str(raw.get("name") or "")
    if not name:
        raise SkillYamlError(
            FrameworkError(
                summary="skill.yaml: missing required field `name`",
                detail=f"path: {path}",
                fix=(
                    "Add `name: <your-skill-name>` as the first line of skill.yaml. "
                    "It should match the `name:` in SKILL.md."
                ),
            )
        )

    strictness_raw = str(raw.get("strictness") or "local")
    strictness = Strictness.from_string(strictness_raw)

    version = str(raw.get("version") or "0.1.0")
    marketplace = raw.get("marketplace")

    ownership: OwnershipRef | None = None
    if raw_own := raw.get("ownership"):
        if isinstance(raw_own, dict):
            ownership = OwnershipRef(
                team=raw_own.get("team"),
                contact=raw_own.get("contact"),
                runbook=raw_own.get("runbook"),
            )

    output_contract: OutputContract | None = None
    if raw_oc := raw.get("output_contract"):
        if isinstance(raw_oc, dict):
            output_contract = OutputContract(
                output=raw_oc.get("output", {}),
                input=raw_oc.get("input", {}),
            )

    model_compat = raw.get("model_compatibility", [])
    if not isinstance(model_compat, list):
        model_compat = []

    raw_policies = raw.get("policies", [])
    if not isinstance(raw_policies, list):
        raw_policies = []
    policies = [str(p) for p in raw_policies if p is not None and str(p).strip()]

    risk = _parse_risk(raw.get("risk"))
    provenance = _parse_provenance(raw.get("provenance"))

    return SkillOverlay(
        name=name,
        strictness=strictness,
        version=version,
        ownership=ownership,
        marketplace=str(marketplace) if marketplace else None,
        output_contract=output_contract,
        model_compatibility=model_compat,
        policies=policies,
        risk=risk,
        provenance=provenance,
        extra=extra,
    )


def _parse_risk(raw: Any) -> Risk:
    """Parse the `risk:` block. Unknown enum values fall through as None."""
    if not isinstance(raw, dict):
        return Risk()
    return Risk(
        level=RiskLevel.from_string(raw.get("level")),
        data_classification=DataClassification.from_string(
            raw.get("data_classification")
        ),
        side_effects=SideEffects.from_string(raw.get("side_effects")),
        requires_human_approval=bool(raw.get("requires_human_approval", False)),
    )


def _parse_provenance(raw: Any) -> Provenance:
    """Parse the `provenance:` block. Tolerant on bad dates (drops to None)."""
    if not isinstance(raw, dict):
        return Provenance()
    return Provenance(
        source_repo=str(raw.get("source_repo") or ""),
        commit_sha=str(raw.get("commit_sha") or ""),
        source_repo_branch=str(raw.get("source_repo_branch") or ""),
        approved_by=str(raw.get("approved_by") or ""),
        approved_at=_parse_provenance_date(raw.get("approved_at")),
        build_tool=str(raw.get("build_tool") or ""),
    )


def _parse_provenance_date(value: Any) -> date | None:
    """ISO date or None — silently drops bad values (publish gate enforces)."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def write_skill_yaml(path: Path, overlay: SkillOverlay) -> None:
    """Serialise a SkillOverlay to `path` as YAML.

    Used by `bbsctl strictness` to scaffold / update skill.yaml.
    """
    data: dict[str, Any] = {
        "name": overlay.name,
        "strictness": overlay.strictness.value,
        "version": overlay.version,
    }
    if overlay.marketplace:
        data["marketplace"] = overlay.marketplace
    if overlay.ownership:
        own: dict[str, Any] = {}
        if overlay.ownership.team:
            own["team"] = overlay.ownership.team
        if overlay.ownership.contact:
            own["contact"] = overlay.ownership.contact
        if overlay.ownership.runbook:
            own["runbook"] = overlay.ownership.runbook
        if own:
            data["ownership"] = own
    if overlay.output_contract:
        oc: dict[str, Any] = {}
        if overlay.output_contract.output:
            oc["output"] = overlay.output_contract.output
        if overlay.output_contract.input:
            oc["input"] = overlay.output_contract.input
        if oc:
            data["output_contract"] = oc
    if overlay.model_compatibility:
        data["model_compatibility"] = overlay.model_compatibility
    if overlay.policies:
        data["policies"] = list(overlay.policies)
    if overlay.risk.declared:
        risk_block: dict[str, Any] = {}
        if overlay.risk.level is not None:
            risk_block["level"] = overlay.risk.level.value
        if overlay.risk.data_classification is not None:
            risk_block["data_classification"] = overlay.risk.data_classification.value
        if overlay.risk.side_effects is not None:
            risk_block["side_effects"] = overlay.risk.side_effects.value
        if overlay.risk.requires_human_approval:
            risk_block["requires_human_approval"] = True
        data["risk"] = risk_block
    if overlay.provenance.declared:
        prov_block: dict[str, Any] = {}
        if overlay.provenance.source_repo:
            prov_block["source_repo"] = overlay.provenance.source_repo
        if overlay.provenance.commit_sha:
            prov_block["commit_sha"] = overlay.provenance.commit_sha
        if overlay.provenance.source_repo_branch:
            prov_block["source_repo_branch"] = overlay.provenance.source_repo_branch
        if overlay.provenance.approved_by:
            prov_block["approved_by"] = overlay.provenance.approved_by
        if overlay.provenance.approved_at is not None:
            prov_block["approved_at"] = overlay.provenance.approved_at.isoformat()
        if overlay.provenance.build_tool:
            prov_block["build_tool"] = overlay.provenance.build_tool
        data["provenance"] = prov_block
    data.update(overlay.extra)

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    with path.open("w", encoding="utf-8") as fh:
        fh.write("# Bulbasaur enterprise overlay — see docs/strictness-levels.md\n")
        yaml.dump(data, fh)


__all__ = [
    "DataClassification",
    "OutputContract",
    "OwnershipRef",
    "Provenance",
    "Risk",
    "RiskLevel",
    "SideEffects",
    "SkillOverlay",
    "SkillYamlError",
    "load_skill_yaml",
    "write_skill_yaml",
]
