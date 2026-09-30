"""ManifestConverter — parses manifest.yml and generates Claude Code descriptors."""

from __future__ import annotations

import re
import os
import json
from pathlib import Path
from typing import Any
from ruamel.yaml import YAML

from skillctl.messaging import FrameworkError, emit, info
from skillctl.strictness import Strictness

CLAUDE_RESERVED_MARKETPLACE_NAMES = {
    "claude-code-marketplace",
    "claude-code-plugins",
    "claude-plugins-official",
    "claude-plugins-community",
    "claude-community",
    "anthropic-marketplace",
    "anthropic-plugins",
    "agent-skills",
    "anthropic-agent-skills",
    "knowledge-work-plugins",
    "life-sciences",
    "claude-for-legal",
    "claude-for-financial-services",
    "financial-services-plugins",
    "first-party-plugins",
    "healthcare",
}

IMPERSONATION_PATTERNS = ["official-claude", "anthropic-plugins-v", "claude-official"]

class ManifestConverterError(Exception):
    """Exception raised when manifest parsing or conversion fails."""
    def __init__(self, framework_error: FrameworkError) -> None:
        self.framework_error = framework_error
        super().__init__(framework_error.summary)


class ManifestConverter:
    """Converts OIC manifest.yml to Claude Code plugin.json and marketplace.json entries."""

    def __init__(self, skill_dir: Path) -> None:
        self.skill_dir = skill_dir.resolve()
        self.manifest_path = self.skill_dir / "manifest.yml"
        self._manifest_cache: dict[str, Any] | None = None

    def load_manifest(self) -> dict[str, Any]:
        """Load and cache the manifest.yml file."""
        if self._manifest_cache is not None:
            return self._manifest_cache

        if not self.manifest_path.exists():
            raise ManifestConverterError(
                FrameworkError(
                    summary=f"manifest.yml not found at {self.manifest_path}",
                    fix="Create a valid OIC `manifest.yml` in the skill directory.",
                )
            )

        yaml = YAML(typ="safe")
        try:
            raw = yaml.load(self.manifest_path)
        except Exception as exc:
            raise ManifestConverterError(
                FrameworkError(
                    summary="manifest.yml: YAML parse error",
                    detail=str(exc),
                    fix="Fix the YAML syntax in manifest.yml.",
                )
            )

        if not isinstance(raw, dict):
            raise ManifestConverterError(
                FrameworkError(
                    summary="manifest.yml: must be a YAML mapping at the top level",
                    fix="Structure your manifest.yml with key-value pairs.",
                )
            )

        self._manifest_cache = raw
        return raw

    def validate_marketplace_name(self, name: str) -> None:
        """Check proposed name against the Claude Code reserved block and impersonation attempts."""
        normalized_name = name.strip().lower()
        if normalized_name in CLAUDE_RESERVED_MARKETPLACE_NAMES:
            raise ManifestConverterError(
                FrameworkError(
                    summary=f"Marketplace name '{name}' is reserved for official Anthropic use.",
                    detail="This name will trigger a 'registered from an untrusted source' load failure in Claude Code.",
                    fix="Choose a different name (e.g., 'ibm-' prefix or 'company-platform-tools').",
                )
            )

        for pattern in IMPERSONATION_PATTERNS:
            if pattern in normalized_name:
                raise ManifestConverterError(
                    FrameworkError(
                        summary=f"Marketplace name '{name}' appears to impersonate an official Anthropic source.",
                        detail="Impersonation names are blocked at load time by Claude Code's runtime rules.",
                        fix="Choose a name that does not contain 'official-claude', 'anthropic-plugins-v', or 'claude-official'.",
                    )
                )

    def validate(self) -> list[str]:
        """Run the 6-checkpoint validation pipeline. Returns warning list."""
        manifest = self.load_manifest()
        warnings: list[str] = []

        # 1. Name Check (Reserved / Pattern match)
        name = manifest.get("name")
        if not name:
            raise ManifestConverterError(
                FrameworkError(
                    summary="manifest.yml: missing required field `name`",
                    fix="Add `name: <your-plugin-name>` to your manifest.yml.",
                )
            )
        self.validate_marketplace_name(name)

        # 2. Version SemVer Check
        version = str(manifest.get("version") or "")
        if not version:
            raise ManifestConverterError(
                FrameworkError(
                    summary="manifest.yml: missing required field `version`",
                    fix="Add a SemVer-compliant version, e.g., `version: 1.0.0`.",
                )
            )
        semver_regex = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
        if not re.match(semver_regex, version):
            raise ManifestConverterError(
                FrameworkError(
                    summary=f"manifest.yml: version '{version}' is not SemVer-compliant",
                    fix="Use a valid SemVer version like 1.2.4.",
                )
            )

        # 3. Status check (active/deprecated/archived)
        status = str(manifest.get("status") or "").strip().lower()
        if status in ("deprecated", "archived"):
            raise ManifestConverterError(
                FrameworkError(
                    summary=f"manifest.yml: asset status is '{status}'",
                    detail="Assets marked as 'deprecated' or 'archived' cannot be published.",
                    fix="Change the status in manifest.yml to 'active' or remove from publication.",
                )
            )

        # 4. Promotion Check for Org-Level Assets
        level = str(manifest.get("level") or "").strip().lower()
        if level == "org":
            promotion = manifest.get("promotion") or {}
            if not isinstance(promotion, dict) or not promotion.get("approved"):
                raise ManifestConverterError(
                    FrameworkError(
                        summary="publish failed: governance gate violation",
                        detail=f"Asset '{name}' requires org-level approval but 'promotion.approved' is currently empty (NULL).",
                        fix="Submit your asset for approval via the OIC platform or run with local-tier settings.",
                    )
                )

        # 5. Type Check (must be skill or mcp-server)
        asset_type = str(manifest.get("type") or "").strip().lower()
        if asset_type == "library":
            raise ManifestConverterError(
                FrameworkError(
                    summary="manifest.yml: asset type is 'library'",
                    detail="Library type assets do not declare a runnable interface or components and are skipped for compilation.",
                    fix="Only 'skill' or 'mcp-server' assets can be compiled to Claude Code plugins.",
                )
            )
        elif asset_type not in ("skill", "mcp-server"):
            raise ManifestConverterError(
                FrameworkError(
                    summary=f"manifest.yml: unsupported asset type '{asset_type}'",
                    fix="Supported types are 'skill' or 'mcp-server'.",
                )
            )

        # 6. Basic completeness / owner warnings
        owners = manifest.get("owners", [])
        if not owners:
            warnings.append("No owners declared in manifest.yml. Falling back to current shell user.")

        return warnings

    def derive_strict_mode(self) -> bool:
        """Derive strict mode boolean field.

        strict: True  -> plugin.json in the plugin's own repo is authoritative.
        strict: False -> Marketplace entry is sole authority. Used for external org-curated raw repos.
        """
        manifest = self.load_manifest()
        is_external = manifest.get("hosting") == "linked" and manifest.get("source_repo")
        is_org_curated = manifest.get("level") == "org"

        if is_external and is_org_curated:
            return False
        return True

    def emit_hooks_config(self, plugin_name: str) -> dict[str, Any]:
        """Generates hooks configuration with ${CLAUDE_PLUGIN_ROOT} substitution."""
        manifest = self.load_manifest()
        hooks = {}
        if manifest.get("hooks", {}).get("post_tool_use"):
            hooks["PostToolUse"] = [
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh"
                        }
                    ]
                }
            ]
        return hooks

    def emit_mcp_server_config(self) -> dict[str, Any]:
        """Generates MCP server configuration with ${CLAUDE_PLUGIN_ROOT} substitution."""
        manifest = self.load_manifest()
        servers = {}
        if manifest.get("type") == "mcp-server":
            server_name = manifest["name"].replace("-", "_")
            servers[server_name] = {
                "command": "${CLAUDE_PLUGIN_ROOT}/bin/server",
                "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/config.json"]
            }
        return servers

    def convert_to_plugin_json(self) -> dict[str, Any]:
        """Convert manifest.yml fields to a standard plugin.json descriptor."""
        manifest = self.load_manifest()

        raw_name = manifest.get("name") or ""
        name = raw_name.lower().replace(" ", "-")
        if not name.endswith("-plugin"):
            name = f"{name}-plugin"

        version = manifest.get("version", "0.1.0")
        description = manifest.get("title") or manifest.get("description") or ""

        # Handle author mapping
        owners = manifest.get("owners", [])
        author_name = "anonymous"
        if owners and isinstance(owners, list):
            author_name = str(owners[0]).lstrip("@")
        elif os.environ.get("USER"):
            author_name = os.environ.get("USER")

        author: dict[str, str] = {"name": author_name}
        if manifest.get("hosting") == "linked" and manifest.get("source_repo"):
            author["url"] = manifest["source_repo"]

        # Keywords normalized (capitalized)
        tags = manifest.get("tags", [])
        keywords = []
        if isinstance(tags, list):
            keywords = [str(t).strip().capitalize() for t in tags]

        # Contributors
        contributors = []
        if len(owners) > 1:
            contributors.extend([str(o).lstrip("@") for o in owners[1:]])
        raw_contribs = manifest.get("contributors", [])
        if isinstance(raw_contribs, list):
            contributors.extend([str(c).lstrip("@") for c in raw_contribs])

        plugin_json: dict[str, Any] = {
            "name": name,
            "version": version,
            "description": description,
            "author": author,
        }

        if keywords:
            plugin_json["keywords"] = keywords
        if contributors:
            plugin_json["contributors"] = contributors

        # Component Routing: If type: skill, point to SKILL.md
        asset_type = manifest.get("type", "skill")
        if asset_type == "skill":
            plugin_json["skills"] = [f"./skills/{raw_name}/SKILL.md"]

        # Merge hooks and servers if present
        hooks = self.emit_hooks_config(name)
        if hooks:
            plugin_json["hooks"] = hooks

        servers = self.emit_mcp_server_config()
        if servers:
            plugin_json["mcpServers"] = servers

        return plugin_json

    def convert_to_marketplace_entry(self, strict: bool | None = None) -> dict[str, Any]:
        """Convert manifest.yml to an entry for marketplace.json."""
        manifest = self.load_manifest()

        raw_name = manifest.get("name") or ""
        name = raw_name.lower().replace(" ", "-")
        if not name.endswith("-plugin"):
            name = f"{name}-plugin"

        if strict is None:
            strict = self.derive_strict_mode()

        version = manifest.get("version", "0.1.0")
        description = manifest.get("title") or manifest.get("description") or ""

        # Author name mapping
        owners = manifest.get("owners", [])
        author_name = "anonymous"
        if owners and isinstance(owners, list):
            author_name = str(owners[0]).lstrip("@")
        elif os.environ.get("USER"):
            author_name = os.environ.get("USER")

        # Category mapping from first tag
        category = None
        tags = manifest.get("tags", [])
        if tags and isinstance(tags, list):
            first_tag = str(tags[0]).lower().strip()
            if first_tag in ("productivity", "security", "devops"):
                category = first_tag

        entry: dict[str, Any] = {
            "name": name,
            "displayName": manifest.get("title") or name,
            "source": name,
            "version": version,
            "description": description,
            "author": {"name": author_name},
            "strict": strict,
            "defaultEnabled": True,
        }

        # Keywords normalized (capitalized)
        keywords = []
        if isinstance(tags, list):
            keywords = [str(t).strip().capitalize() for t in tags]
        if keywords:
            entry["keywords"] = keywords

        if category:
            entry["category"] = category

        # If type: skill, declare skills component
        asset_type = manifest.get("type", "skill")
        if asset_type == "skill":
            entry["skills"] = [f"./skills/{raw_name}/SKILL.md"]

        return entry


def verify_strict_mode_conflict(plugin_dir: Path, strict: bool) -> None:
    """When strict=False, verifies the plugin.json (if present) does not declare components."""
    if strict:
        return

    plugin_json_path = plugin_dir / ".claude-plugin" / "plugin.json"
    if not plugin_json_path.exists():
        return

    try:
        with open(plugin_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return # skip invalid json, separate validation will capture it

    COMPONENT_FIELDS = {"skills", "commands", "agents", "hooks", "mcpServers", "lspServers"}
    conflicting = COMPONENT_FIELDS.intersection(data.keys())
    if conflicting:
        raise ManifestConverterError(
            FrameworkError(
                summary="strict mode conflict detected",
                detail=f"strict: false is set in the marketplace entry for '{plugin_dir.name}', but the plugin's own plugin.json declares components: {conflicting}.",
                fix="Either remove the component fields from plugin.json or set strict: true.",
            )
        )
