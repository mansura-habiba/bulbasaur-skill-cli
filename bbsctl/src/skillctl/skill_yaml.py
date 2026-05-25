"""skill.yaml — the enterprise overlay sibling to SKILL.md.

`skill.yaml` is the Phase 2+ enterprise overlay that sits beside `SKILL.md` in
a skill directory. At `local` strictness it is optional; at `team` it is
required. It carries the fields the public agentskills.io spec does not define:
strictness, ownership ref, marketplace config, output contract, model compat.

See: framework-build-plan.md §1, ADR 0003, ADR 0007.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
             "output_contract", "model_compatibility"}
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

    return SkillOverlay(
        name=name,
        strictness=strictness,
        version=version,
        ownership=ownership,
        marketplace=str(marketplace) if marketplace else None,
        output_contract=output_contract,
        model_compatibility=model_compat,
        extra=extra,
    )


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
    data.update(overlay.extra)

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    with path.open("w", encoding="utf-8") as fh:
        fh.write("# Bulbasaur enterprise overlay — see docs/strictness-levels.md\n")
        yaml.dump(data, fh)


__all__ = [
    "OutputContract",
    "OwnershipRef",
    "SkillOverlay",
    "SkillYamlError",
    "load_skill_yaml",
    "write_skill_yaml",
]
