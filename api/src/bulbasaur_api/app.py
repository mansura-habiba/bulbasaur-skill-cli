"""Single FastMCP server: MCP tool and REST HTTP route share a validator.

Local development only. FastMCP custom HTTP routes bypass MCP auth; the
REST route has its own bearer check, while the MCP endpoint binds to loopback.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from pathlib import Path

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from skillctl.agentskills.frontmatter import parse_skill_md

MAX_SKILL_BYTES = 128 * 1024
MAX_REQUEST_BYTES = MAX_SKILL_BYTES + 4096
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_skill(skill_name: str, skill_md: str) -> dict:
    """Validate Agent Skills frontmatter; no execution or security approval."""
    if not isinstance(skill_name, str) or not isinstance(skill_md, str):
        return {
            "status": "failed", "artifact_sha256": "",
            "validator": "agentskills-frontmatter",
            "findings": [{"code": "invalid_input", "message": "Expected string inputs"}],
        }
    raw = skill_md.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    base = {"artifact_sha256": digest, "validator": "agentskills-frontmatter"}
    if len(raw) > MAX_SKILL_BYTES:
        return {**base, "status": "failed", "findings": [
            {"code": "size_limit", "message": "SKILL.md exceeds 128 KiB"}]}
    if len(skill_name) > 64 or not _NAME.fullmatch(skill_name):
        return {**base, "status": "failed", "findings": [
            {"code": "invalid_name", "message": "Expected a lowercase kebab-case skill name"}]}
    try:
        with tempfile.TemporaryDirectory(prefix="bulbasaur-validate-") as root:
            directory = Path(root) / skill_name
            directory.mkdir()
            file = directory / "SKILL.md"
            file.write_bytes(raw)
            parse_skill_md(file)
    except Exception:
        # Never echo parser errors that may contain uploaded text or temp paths.
        return {**base, "status": "failed", "findings": [
            {"code": "invalid_skill", "message": "SKILL.md failed Agent Skills validation"}]}
    return {**base, "status": "passed", "findings": []}


def create_app() -> FastMCP:
    """Make the combined server with two entry points and one validation core."""
    server = FastMCP("Bulbasaur Skill Validation")

    @server.tool
    def validate_agent_skill(skill_name: str, skill_md: str) -> dict:
        """Validate SKILL.md structure without running or approving the skill."""
        return validate_skill(skill_name, skill_md)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @server.custom_route("/v1/skills/validate", methods=["POST"])
    async def validate_http(request: Request) -> JSONResponse:
        # FastMCP AuthProvider does not protect custom HTTP routes.
        token = os.environ.get("BULBASAUR_HTTP_TOKEN", "")
        supplied = request.headers.get("authorization", "")
        if not token or not hmac.compare_digest(supplied, "Bearer " + token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > MAX_REQUEST_BYTES:
                    return JSONResponse({"error": "request_too_large"}, status_code=413)
            except ValueError:
                return JSONResponse({"error": "invalid_content_length"}, status_code=400)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                return JSONResponse({"error": "request_too_large"}, status_code=413)
            body.extend(chunk)
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(data, dict):
            return JSONResponse({"error": "expected_object"}, status_code=400)
        return JSONResponse(validate_skill(data.get("skill_name"), data.get("skill_md")))

    return server


mcp = create_app()
