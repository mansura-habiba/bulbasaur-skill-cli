"""Tests for the user/org config cascade.

Covers `~/.config/bbsctl/config.yaml`, `/etc/bbsctl/config.yaml`,
`BBSCTL_USER_CONFIG`, `BBSCTL_ORG_CONFIG`, env-var overrides per field,
and the merged EvalConfig that lands in EvalRunner.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from skillctl.user_config import (
    llm_backend_config,
    load_layered_eval_defaults,
    load_yaml_dict,
    org_config_path,
    user_config_path,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content), encoding="utf-8")


# ── path resolution ───────────────────────────────────────────────────────


def test_user_config_path_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("BBSCTL_USER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert user_config_path() == tmp_path / "bbsctl" / "config.yaml"


def test_user_config_path_respects_explicit_file(monkeypatch, tmp_path):
    override = tmp_path / "my-config.yaml"
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(override))
    assert user_config_path() == override


def test_org_config_path_none_when_absent(monkeypatch):
    monkeypatch.delenv("BBSCTL_ORG_CONFIG", raising=False)
    # /etc/bbsctl/config.yaml almost certainly doesn't exist in CI.
    p = org_config_path()
    if p is not None:
        # If it exists in the CI image, that's fine; just sanity-check path.
        assert p.name.endswith("config.yaml")


def test_org_config_path_respects_env_override(monkeypatch, tmp_path):
    override = tmp_path / "org.yaml"
    override.write_text("eval:\n  runtime: mock\n", encoding="utf-8")
    monkeypatch.setenv("BBSCTL_ORG_CONFIG", str(override))
    assert org_config_path() == override


# ── load_yaml_dict ────────────────────────────────────────────────────────


def test_load_yaml_dict_returns_empty_when_absent(tmp_path):
    assert load_yaml_dict(tmp_path / "nope.yaml") == {}


def test_load_yaml_dict_returns_empty_on_malformed(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("foo: [unbalanced\n", encoding="utf-8")
    # Loader is forgiving — never crashes startup.
    assert load_yaml_dict(p) == {}


def test_load_yaml_dict_returns_dict_on_well_formed(tmp_path):
    p = tmp_path / "good.yaml"
    p.write_text("foo: bar\nnum: 42\n", encoding="utf-8")
    result = load_yaml_dict(p)
    assert result == {"foo": "bar", "num": 42}


# ── layered defaults ──────────────────────────────────────────────────────


def test_load_layered_defaults_uses_built_in_when_no_files(monkeypatch, tmp_path):
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(tmp_path / "no.yaml"))
    monkeypatch.delenv("BBSCTL_ORG_CONFIG", raising=False)
    for env in (
        "BBSCTL_EVAL_RUNTIME",
        "BBSCTL_EVAL_RUNTIME_MODEL",
        "BBSCTL_RUNTIME_MODEL",
        "BBSCTL_EVAL_JUDGE",
        "BBSCTL_EVAL_THRESHOLD",
    ):
        monkeypatch.delenv(env, raising=False)
    cfg = load_layered_eval_defaults()
    assert cfg.runtime == "mock"
    assert cfg.judge == "heuristic"
    assert cfg.threshold == 1.0


def test_user_layer_overrides_built_in(monkeypatch, tmp_path):
    user_file = tmp_path / "config.yaml"
    _write(user_file, """\
        eval:
          runtime: claude-agent-sdk
          runtime_model: claude-sonnet-4-6
          judge: llm
          judge_threshold: 0.7
          threshold: 0.95
          fuzz_n_variants: 8
    """)
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(user_file))
    monkeypatch.delenv("BBSCTL_ORG_CONFIG", raising=False)
    cfg = load_layered_eval_defaults()
    assert cfg.runtime == "claude-agent-sdk"
    assert cfg.runtime_model == "claude-sonnet-4-6"
    assert cfg.judge == "llm"
    assert cfg.judge_threshold == 0.7
    assert cfg.threshold == 0.95
    assert cfg.fuzz_n_variants == 8


def test_org_layer_below_user_layer(monkeypatch, tmp_path):
    org_file = tmp_path / "org.yaml"
    user_file = tmp_path / "user.yaml"
    _write(org_file, """\
        eval:
          runtime: mock
          runtime_model: org-model
          judge: heuristic
    """)
    _write(user_file, """\
        eval:
          runtime_model: user-model
    """)
    monkeypatch.setenv("BBSCTL_ORG_CONFIG", str(org_file))
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(user_file))
    cfg = load_layered_eval_defaults()
    # User wins on overlapping field.
    assert cfg.runtime_model == "user-model"
    # Org provides where user is silent.
    assert cfg.runtime == "mock"
    assert cfg.judge == "heuristic"


def test_env_overrides_user_layer(monkeypatch, tmp_path):
    user_file = tmp_path / "u.yaml"
    _write(user_file, """\
        eval:
          runtime_model: from-file
          threshold: 0.5
    """)
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(user_file))
    monkeypatch.setenv("BBSCTL_EVAL_RUNTIME_MODEL", "from-env")
    monkeypatch.setenv("BBSCTL_EVAL_THRESHOLD", "0.99")
    cfg = load_layered_eval_defaults()
    assert cfg.runtime_model == "from-env"
    assert cfg.threshold == 0.99


def test_short_env_form_works(monkeypatch, tmp_path):
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(tmp_path / "absent.yaml"))
    monkeypatch.delenv("BBSCTL_ORG_CONFIG", raising=False)
    monkeypatch.delenv("BBSCTL_EVAL_RUNTIME_MODEL", raising=False)
    monkeypatch.setenv("BBSCTL_RUNTIME_MODEL", "claude-haiku-4-5-20251001")
    cfg = load_layered_eval_defaults()
    assert cfg.runtime_model == "claude-haiku-4-5-20251001"


def test_long_env_takes_precedence_over_short(monkeypatch, tmp_path):
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(tmp_path / "absent.yaml"))
    monkeypatch.delenv("BBSCTL_ORG_CONFIG", raising=False)
    monkeypatch.setenv("BBSCTL_EVAL_RUNTIME_MODEL", "long-form-wins")
    monkeypatch.setenv("BBSCTL_RUNTIME_MODEL", "short-form-loses")
    cfg = load_layered_eval_defaults()
    assert cfg.runtime_model == "long-form-wins"


# ── llm_backend_config ────────────────────────────────────────────────────


def test_llm_backend_config_merges_org_and_user(monkeypatch, tmp_path):
    org_file = tmp_path / "org.yaml"
    user_file = tmp_path / "user.yaml"
    _write(org_file, """\
        llm_backends:
          ollama:
            host: http://org-server:11434
            default_model: org-llama
    """)
    _write(user_file, """\
        llm_backends:
          ollama:
            default_model: user-llama
    """)
    monkeypatch.setenv("BBSCTL_ORG_CONFIG", str(org_file))
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(user_file))
    cfg = llm_backend_config("ollama")
    # User overrides default_model.
    assert cfg["default_model"] == "user-llama"
    # Org provides host where user is silent.
    assert cfg["host"] == "http://org-server:11434"


def test_llm_backend_config_returns_empty_for_unknown_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(tmp_path / "absent.yaml"))
    monkeypatch.delenv("BBSCTL_ORG_CONFIG", raising=False)
    assert llm_backend_config("nonexistent") == {}


# ── integration: EvalRunner picks up the cascade ──────────────────────────


def test_eval_runner_uses_user_layer_when_no_skill_config(monkeypatch, tmp_path):
    """End-to-end: a user-level config drives EvalRunner when the skill has no
    eval.config.yaml of its own."""
    import json

    from skillctl.eval import EvalRunner
    from skillctl.eval.reproducibility import load_eval_config
    from skillctl.strictness import Strictness

    user_file = tmp_path / "config.yaml"
    _write(user_file, """\
        eval:
          runtime: mock
          runtime_model: user-pinned-model
          judge_threshold: 0.1
          threshold: 0.5
    """)
    monkeypatch.setenv("BBSCTL_USER_CONFIG", str(user_file))
    monkeypatch.delenv("BBSCTL_ORG_CONFIG", raising=False)

    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: s\ndescription: test\n---\nReply with: \"answer\"",
        encoding="utf-8",
    )
    (skill / "evals").mkdir()
    (skill / "evals" / "behavior.json").write_text(
        json.dumps(
            {
                "skill_name": "s",
                "evals": [{"id": 1, "prompt": "p", "assertions": ["answer"]}],
            }
        ),
        encoding="utf-8",
    )
    config = load_eval_config(skill)
    assert config.runtime_model == "user-pinned-model"
    assert config.judge_threshold == 0.1
    assert config.threshold == 0.5

    report = EvalRunner(skill, Strictness.LOCAL, config=config).run()
    assert report.runtime_model == "user-pinned-model"
    assert report.threshold == 0.5
