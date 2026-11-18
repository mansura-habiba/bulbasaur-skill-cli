"""Bounded in-memory upload transport over the existing Agent Skills parser.

The API does not approve, install, execute, or publish skills. Uploaded contents
are held only in a private temporary directory while parsing is performed.
"""
from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from skillctl.agentskills.frontmatter import parse_skill_md

_MAX_BYTES = 128 * 1024
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ValidationRequest(BaseModel):
    skill_name: str = Field(min_length=1, max_length=64)
    skill_md: str = Field(min_length=1, max_length=_MAX_BYTES)


class Finding(BaseModel):
    code: str
    message: str


class ValidationResponse(BaseModel):
    status: Literal["passed", "failed"]
    artifact_sha256: str
    validator: str = "agentskills-frontmatter"
    findings: list[Finding] = Field(default_factory=list)


def validate_skill(request: ValidationRequest) -> ValidationResponse:
    """Validate an uploaded SKILL.md with the existing skillctl frontmatter parser.

    This is deliberately a *structural* check, not a full Bulbasaur compile,
    security scan, behavioral evaluation, or Catalog governance decision.
    """
    raw = request.skill_md.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > _MAX_BYTES:
        return ValidationResponse(
            status="failed",
            artifact_sha256=digest,
            findings=[Finding(code="size_limit", message="SKILL.md exceeds 128 KiB")],
        )
    if not _NAME.fullmatch(request.skill_name):
        return ValidationResponse(
            status="failed",
            artifact_sha256=digest,
            findings=[Finding(code="invalid_name", message="Expected a lowercase kebab-case skill name")],
        )
    try:
        with tempfile.TemporaryDirectory(prefix="bulbasaur-validate-") as root:
            directory = Path(root) / request.skill_name
            directory.mkdir()
            path = directory / "SKILL.md"
            path.write_bytes(raw)
            parse_skill_md(path)
    except Exception:
        # Do not reflect parsing exception details: they may include uploaded
        # content or local paths. Rich diagnostics can be added via a scrubber.
        return ValidationResponse(
            status="failed",
            artifact_sha256=digest,
            findings=[Finding(code="invalid_skill", message="SKILL.md failed Agent Skills validation")],
        )
    return ValidationResponse(status="passed", artifact_sha256=digest)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bulbasaur Assessment API",
        version="0.1.0",
        description="Structural Skill validation only. No execution, installation or approval.",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/skills/validate", response_model=ValidationResponse)
    def validate(request: ValidationRequest) -> ValidationResponse:
        return validate_skill(request)

    return app


app = create_app()
