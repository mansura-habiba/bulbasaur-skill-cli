"""Tests for the ownership module."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from skillctl.ownership import (
    Escalation,
    OnCall,
    Ownership,
    OwnershipLoadError,
    load_ownership,
)


def _write(tmp_path: Path, content: str) -> None:
    (tmp_path / "ownership.yaml").write_text(dedent(content), encoding="utf-8")


def test_load_returns_none_when_absent(tmp_path):
    assert load_ownership(tmp_path) is None


def test_load_parses_team_minimum(tmp_path):
    _write(tmp_path, """\
        schema_version: bulbasaur/v1
        skill: mq-executor
        team: mq-platform
        contact: mq-platform@example.com
    """)
    o = load_ownership(tmp_path)
    assert o.team == "mq-platform"
    assert o.contact == "mq-platform@example.com"
    assert o.has_team_minimum is True
    assert o.has_org_minimum is False


def test_load_parses_full_org_schema(tmp_path):
    _write(tmp_path, """\
        schema_version: bulbasaur/v1
        skill: mq-executor
        team: mq-platform
        contact: mq-platform@example.com
        runbook: https://wiki.example.com/runbooks/mq-restart
        on_call:
          rotation: pagerduty:mq-primary
          escalation_minutes: 15
        escalation:
          - tier: 2
            contact: manager@example.com
            within_minutes: 30
          - tier: 1
            contact: oncall@example.com
            within_minutes: 0
        cost_owner: cost-center-1234
        business_owner: jane.doe@example.com
        last_reviewed: 2026-05-30
    """)
    o = load_ownership(tmp_path)
    assert o.has_org_minimum is True
    assert o.on_call == OnCall(rotation="pagerduty:mq-primary", escalation_minutes=15)
    # escalation sorted by tier ascending
    assert [e.tier for e in o.escalation] == [1, 2]
    assert o.last_reviewed == date(2026, 5, 30)


def test_load_rejects_escalation_missing_tier(tmp_path):
    _write(tmp_path, """\
        skill: x
        escalation:
          - contact: a@example.com
    """)
    with pytest.raises(OwnershipLoadError) as exc:
        load_ownership(tmp_path)
    assert "missing `tier`" in exc.value.framework_error.summary


def test_load_rejects_escalation_missing_contact(tmp_path):
    _write(tmp_path, """\
        skill: x
        escalation:
          - tier: 1
    """)
    with pytest.raises(OwnershipLoadError) as exc:
        load_ownership(tmp_path)
    assert "missing `contact`" in exc.value.framework_error.summary


def test_load_rejects_bad_date_format(tmp_path):
    _write(tmp_path, """\
        skill: x
        last_reviewed: "not a date"
    """)
    with pytest.raises(OwnershipLoadError) as exc:
        load_ownership(tmp_path)
    assert "ISO date" in exc.value.framework_error.summary


def test_load_rejects_malformed_yaml(tmp_path):
    (tmp_path / "ownership.yaml").write_text("foo: [unbalanced", encoding="utf-8")
    with pytest.raises(OwnershipLoadError) as exc:
        load_ownership(tmp_path)
    assert "YAML parse error" in exc.value.framework_error.summary


def test_has_team_minimum_requires_both_fields():
    assert not Ownership(team="x").has_team_minimum
    assert not Ownership(contact="x@y").has_team_minimum
    assert Ownership(team="x", contact="x@y").has_team_minimum


def test_has_org_minimum_requires_all_fields():
    base = Ownership(
        team="x",
        contact="x@y",
        runbook="https://x",
        on_call=OnCall(rotation="r"),
        escalation=[Escalation(tier=1, contact="a@b")],
        cost_owner="cc-1",
        business_owner="b@c",
    )
    assert base.has_org_minimum
    # remove any single field → fails
    assert not Ownership(
        team="x", contact="x@y", runbook="https://x"
    ).has_org_minimum
