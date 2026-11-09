"""Regression: in-repo Trusted Publisher claims stay aligned for first PyPI upload.

A pending publisher on PyPI only converts after the first successful upload whose
OIDC claims match the pending form (package name, workflow filename, environment).
This test locks the in-repo half of that contract so drift cannot silently leave
the publisher pending again.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "bbsctl" / "pyproject.toml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-publish.yml"

EXPECTED_PACKAGE = "skill-pipeline"
EXPECTED_WORKFLOW_NAME = "python-publish.yml"
EXPECTED_ENVIRONMENT = "pypi"
EXPECTED_SCRIPT = "bbsctl"


def test_pyproject_package_name_matches_pending_publisher() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert data["project"]["name"] == EXPECTED_PACKAGE
    assert data["project"]["scripts"][EXPECTED_SCRIPT] == "skillctl.cli:main"


def test_publish_workflow_filename_matches_pending_publisher_docs() -> None:
    assert WORKFLOW.name == EXPECTED_WORKFLOW_NAME
    assert WORKFLOW.is_file()


def test_publish_job_uses_pypi_environment_and_oidc() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert re.search(
        r"(?m)^  pypi-publish:\s*$",
        text,
    ), "expected a pypi-publish job"

    # Environment name is the OIDC claim PyPI matches against the pending form.
    assert re.search(
        r"(?ms)^  pypi-publish:.*?^\s+environment:\s*\n\s+name:\s*pypi\s*$",
        text,
    ), "pypi-publish must use GitHub environment `pypi`"

    assert re.search(
        r"(?ms)^  pypi-publish:.*?^\s+id-token:\s*write\s*$",
        text,
    ), "pypi-publish must request id-token: write for Trusted Publishing"

    assert "https://pypi.org/p/skill-pipeline" in text
