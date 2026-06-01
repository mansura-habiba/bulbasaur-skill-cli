"""User-level + org-level config layer.

The configuration cascade (highest priority wins):

  1. CLI flag
  2. Environment variable
  3. Skill-level config (evals/eval.config.yaml, skill.yaml, permissions.yaml)
  4. Project-level config (pyproject.toml [tool.bulbasaur.eval])
  5. User-level config (~/.config/bbsctl/config.yaml or $XDG_CONFIG_HOME)
  6. Org-level config (/etc/bbsctl/config.yaml or $BBSCTL_ORG_CONFIG)
  7. Built-in default (dataclass)

This module owns layers 5 and 6 — the cross-project / cross-team defaults a
developer or platform team writes once and forgets about. The other layers
are owned by their respective modules.

Schema (user / org config files):

    schema_version: bulbasaur/v1
    eval:
      runtime: claude-agent-sdk
      runtime_model: claude-sonnet-4-6
      runtime_max_tokens: 4096
      runtime_temperature: 0.0
      judge: llm
      judge_backend: ollama
      judge_model: llama3:8b
      judge_threshold: 0.5
      judge_max_tokens: 256
      threshold: 1.0
      fuzz_n_variants: 4
    llm_backends:
      ollama:
        host: http://localhost:11434
        default_model: llama3:8b
      anthropic:
        default_model: claude-sonnet-4-6
      openai:
        api_base: https://api.openai.com/v1
        default_model: gpt-4o-mini

Every field is optional — absent fields fall through to the built-in
defaults. The user file is read-write; the org file is typically managed by
the platform team.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# Imported lazily inside the loader to break circular import with the eval module.


def user_config_path() -> Path:
    """Resolve the user-level config path."""
    base = (
        os.environ.get("BBSCTL_USER_CONFIG")
        or os.environ.get("XDG_CONFIG_HOME")
        or os.path.expanduser("~/.config")
    )
    # If BBSCTL_USER_CONFIG points at a file directly, honour it; otherwise
    # treat as a config root.
    base_path = Path(base)
    if base_path.suffix in {".yaml", ".yml"}:
        return base_path
    return base_path / "bbsctl" / "config.yaml"


def org_config_path() -> Path | None:
    """Resolve the org-level config path. None if neither candidate exists."""
    env_override = os.environ.get("BBSCTL_ORG_CONFIG")
    if env_override:
        p = Path(env_override)
        return p if p.exists() else None
    p = Path("/etc/bbsctl/config.yaml")
    return p if p.exists() else None


def load_yaml_dict(path: Path) -> dict[str, Any]:
    """Read a YAML file and return the top-level dict, or {} on failure.

    Loader is forgiving: a malformed or missing config never crashes startup.
    The validator (`bbsctl config check`) is where syntax errors surface
    loudly.
    """
    if not path.exists():
        return {}
    try:
        yaml = YAML(typ="safe")
        data = yaml.load(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_layered_eval_defaults():
    """Build an `EvalConfig` from org + user layers, applying env overrides.

    Returns an `EvalConfig` populated from the configuration cascade. The
    skill-level config layer is applied above this by `load_eval_config`
    in `eval/reproducibility.py`. CLI overrides apply above that.
    """
    from skillctl.eval.reproducibility import EvalConfig

    org = load_yaml_dict(org_config_path()) if org_config_path() else {}
    user = load_yaml_dict(user_config_path())

    # User-layer overrides org-layer.
    merged: dict[str, Any] = {}
    for layer in (org, user):
        eval_section = layer.get("eval", {}) if isinstance(layer, dict) else {}
        if isinstance(eval_section, dict):
            for key, value in eval_section.items():
                if value is not None and value != "":
                    merged[key] = value

    # Apply env-var overrides on top of the file layers.
    _apply_env_overrides(merged)

    return _build_eval_config(merged, EvalConfig)


def _apply_env_overrides(target: dict[str, Any]) -> None:
    """Read BBSCTL_* env vars and write into the target dict.

    Every EvalConfig field can be overridden by an env var of the form
    `BBSCTL_EVAL_<FIELD_UPPER>`. Example: `BBSCTL_EVAL_RUNTIME_MODEL`,
    `BBSCTL_EVAL_JUDGE_THRESHOLD`. Short aliases (e.g. `BBSCTL_RUNTIME_MODEL`
    without the `EVAL_` segment) are also honoured for the most-used fields
    so the env surface is friendly.
    """
    long_form = {
        "runtime": "BBSCTL_EVAL_RUNTIME",
        "runtime_model": "BBSCTL_EVAL_RUNTIME_MODEL",
        "runtime_max_tokens": "BBSCTL_EVAL_RUNTIME_MAX_TOKENS",
        "runtime_temperature": "BBSCTL_EVAL_RUNTIME_TEMPERATURE",
        "judge": "BBSCTL_EVAL_JUDGE",
        "judge_backend": "BBSCTL_EVAL_JUDGE_BACKEND",
        "judge_model": "BBSCTL_EVAL_JUDGE_MODEL",
        "judge_threshold": "BBSCTL_EVAL_JUDGE_THRESHOLD",
        "judge_max_tokens": "BBSCTL_EVAL_JUDGE_MAX_TOKENS",
        "threshold": "BBSCTL_EVAL_THRESHOLD",
        "fuzz_n_variants": "BBSCTL_EVAL_FUZZ_N_VARIANTS",
    }
    short_form = {
        "runtime_model": "BBSCTL_RUNTIME_MODEL",
        "judge_model": "BBSCTL_JUDGE_MODEL",
        "judge_backend": "BBSCTL_JUDGE_BACKEND",
    }

    for field, env_name in long_form.items():
        if (v := os.environ.get(env_name)) is not None and v != "":
            target[field] = v
    for field, env_name in short_form.items():
        if (v := os.environ.get(env_name)) is not None and v != "":
            target.setdefault(field, v)  # don't override long_form set above


def _build_eval_config(data: dict[str, Any], cls):
    """Coerce a config dict into an EvalConfig with safe type conversion."""
    return cls(
        runtime=str(data.get("runtime") or "mock"),
        runtime_model=str(data.get("runtime_model") or ""),
        runtime_max_tokens=_to_int(data.get("runtime_max_tokens"), default=4096),
        runtime_temperature=_to_float(data.get("runtime_temperature"), default=0.0),
        judge=str(data.get("judge") or "heuristic"),
        judge_backend=str(data.get("judge_backend") or ""),
        judge_model=str(data.get("judge_model") or ""),
        judge_threshold=_to_float(data.get("judge_threshold"), default=0.5),
        judge_max_tokens=_to_int(data.get("judge_max_tokens"), default=256),
        threshold=_to_float(data.get("threshold"), default=1.0),
        fuzz_n_variants=_to_int(data.get("fuzz_n_variants"), default=4),
    )


def _to_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def llm_backend_config(backend_name: str) -> dict[str, Any]:
    """Return the per-backend config slice from the user + org layers.

    Backends consult this for default host/api_base/model when not
    explicitly constructed with overrides.
    """
    out: dict[str, Any] = {}
    org = load_yaml_dict(org_config_path()) if org_config_path() else {}
    user = load_yaml_dict(user_config_path())
    for layer in (org, user):
        backends = layer.get("llm_backends", {}) if isinstance(layer, dict) else {}
        if not isinstance(backends, dict):
            continue
        section = backends.get(backend_name, {})
        if isinstance(section, dict):
            for k, v in section.items():
                if v is not None and v != "":
                    out[k] = v
    return out


__all__ = [
    "llm_backend_config",
    "load_layered_eval_defaults",
    "load_yaml_dict",
    "org_config_path",
    "user_config_path",
]
