"""Read the `[tool.bulbasaur]` section from a project's pyproject.toml.

Uses `tomllib` (stdlib, Python 3.11+) for parsing — no extra dependency.
Searches the directory tree upward from a starting directory so the config
is found whether the command is run from a skill subdirectory or the project root.

See: ADR 0007 — project config in [tool.bulbasaur].
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from skillctl.strictness import Strictness


@dataclass
class SpecLintPolicy:
    """Per-strictness spec-lint disposition. See ADR 0010."""

    local: str = "skip"
    team: str = "warn"
    org: str = "block"
    regulated: str = "block"

    def disposition_for(self, strictness: Strictness) -> str:
        return getattr(self, strictness.value, "warn")


@dataclass
class AuditConfig:
    """Audit log sink configuration. See ADR 0013."""

    team_sink: str = ".bulbasaur/audit.jsonl"
    org_sink: str | None = None
    retention_years: int = 1


@dataclass
class TenantConfig:
    """Tenant isolation config. See ADR 0014."""

    business_unit_id: str | None = None
    environment_id: str = "prod"


@dataclass
class SigningConfig:
    """Signing config. See ADR 0015."""

    mode: str = "online"  # online | offline
    trust_root: str = "sigstore-root"


@dataclass
class ProjectConfig:
    """Validated project-level config from `[tool.bulbasaur]` in pyproject.toml.

    All fields have permissive defaults so local-strictness projects that have
    not yet called `bbsctl init` still get reasonable behaviour.
    """

    version: int = 1
    default_strictness: Strictness = Strictness.LOCAL
    marketplace: str | None = None
    spec_lint: SpecLintPolicy = field(default_factory=SpecLintPolicy)
    audit: AuditConfig = field(default_factory=AuditConfig)
    tenant: TenantConfig = field(default_factory=TenantConfig)
    signing: SigningConfig = field(default_factory=SigningConfig)

    # Path to the pyproject.toml that was loaded, for diagnostics.
    source_path: Path | None = None


_DEFAULTS = ProjectConfig()


def load_project_config(start_dir: Path) -> ProjectConfig:
    """Find and load `[tool.bulbasaur]` from the nearest pyproject.toml.

    Walks up from `start_dir` looking for `pyproject.toml`. If no file is
    found, or the file has no `[tool.bulbasaur]` section, returns default config.
    This is intentional: local-strictness projects need zero project setup.
    """
    pyproject = _find_pyproject(start_dir)
    if pyproject is None:
        return _DEFAULTS

    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return _DEFAULTS

    raw: dict = data.get("tool", {}).get("bulbasaur", {})
    if not raw:
        return ProjectConfig(source_path=pyproject)

    return _parse_config(raw, source_path=pyproject)


def _find_pyproject(start: Path) -> Path | None:
    """Walk up the directory tree from `start`, return the first pyproject.toml found."""
    candidate = start.resolve()
    for _ in range(20):  # cap traversal depth
        p = candidate / "pyproject.toml"
        if p.exists():
            return p
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def _parse_config(raw: dict, *, source_path: Path) -> ProjectConfig:
    version = int(raw.get("version", 1))
    default_strictness = Strictness.from_string(raw.get("default_strictness", "local"))
    marketplace = raw.get("marketplace")

    spec_lint_raw = raw.get("spec_lint", {})
    spec_lint = SpecLintPolicy(
        local=spec_lint_raw.get("local", "skip"),
        team=spec_lint_raw.get("team", "warn"),
        org=spec_lint_raw.get("org", "block"),
        regulated=spec_lint_raw.get("regulated", "block"),
    )

    audit_raw = raw.get("audit", {})
    audit = AuditConfig(
        team_sink=audit_raw.get("team_sink", ".bulbasaur/audit.jsonl"),
        org_sink=audit_raw.get("org_sink"),
        retention_years=int(audit_raw.get("retention_years", 1)),
    )

    tenant_raw = raw.get("tenant", {})
    tenant = TenantConfig(
        business_unit_id=tenant_raw.get("business_unit_id"),
        environment_id=tenant_raw.get("environment_id", "prod"),
    )

    signing_raw = raw.get("signing", {})
    signing = SigningConfig(
        mode=signing_raw.get("mode", "online"),
        trust_root=signing_raw.get("trust_root", "sigstore-root"),
    )

    return ProjectConfig(
        version=version,
        default_strictness=default_strictness,
        marketplace=str(marketplace) if marketplace else None,
        spec_lint=spec_lint,
        audit=audit,
        tenant=tenant,
        signing=signing,
        source_path=source_path,
    )


def render_toml_section(config: ProjectConfig) -> str:
    """Render a `[tool.bulbasaur]` TOML snippet from a ProjectConfig.

    Used by `bbsctl init` to append config to pyproject.toml.
    """
    lines = [
        "",
        "[tool.bulbasaur]",
        f'version = {config.version}',
        f'default_strictness = "{config.default_strictness.value}"',
    ]
    if config.marketplace:
        lines.append(f'marketplace = "{config.marketplace}"')
    lines.append("")
    lines.append("[tool.bulbasaur.spec_lint]")
    lines.append(f'local = "{config.spec_lint.local}"')
    lines.append(f'team = "{config.spec_lint.team}"')
    lines.append(f'org = "{config.spec_lint.org}"')
    lines.append(f'regulated = "{config.spec_lint.regulated}"')
    return "\n".join(lines) + "\n"


__all__ = [
    "AuditConfig",
    "ProjectConfig",
    "SigningConfig",
    "SpecLintPolicy",
    "TenantConfig",
    "load_project_config",
    "render_toml_section",
]
