"""FastMCP HTTP and MCP adapters around a single reusable assessment service.

Custom REST routes have independent authentication; both transports share the
same side-effect-bounded library API. Loopback development only.
"""
from __future__ import annotations

import hmac
import json
import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .service import MAX_SKILL_BYTES, SkillAssessmentService

MAX_REQUEST_BYTES = MAX_SKILL_BYTES + 4096
_service = SkillAssessmentService()


def validate_skill(skill_name: str, skill_md: str) -> dict:
    """Backward-compatible structural validation helper."""
    return _service.validate(skill_name, skill_md)


def assess_skill(skill_name: str, skill_md: str, profile: str = "local") -> dict:
    """Invoke existing Bulbasaur compile/static checks, no model execution."""
    return _service.assess(skill_name, skill_md, profile=profile)


def create_app() -> FastMCP:
    server = FastMCP("Bulbasaur Skill Assessment")

    @server.tool
    def validate_agent_skill(skill_name: str, skill_md: str) -> dict:
        """Validate SKILL.md frontmatter without running or approving a skill."""
        return validate_skill(skill_name, skill_md)

    @server.tool
    def assess_agent_skill(skill_name: str, skill_md: str, profile: str = "local") -> dict:
        """Run structural/static compile checks without model-based evaluation."""
        return assess_skill(skill_name, skill_md, profile)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def _read_authenticated_json(request: Request):
        # Custom routes are not protected by FastMCP MCP authorization.
        token = os.environ.get("BULBASAUR_HTTP_TOKEN", "")
        supplied = request.headers.get("authorization", "")
        if not token or not hmac.compare_digest(supplied, "Bearer " + token):
            return None, JSONResponse({"error": "unauthorized"}, status_code=401)
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) < 0:
                    return None, JSONResponse({"error": "invalid_content_length"}, status_code=400)
                if int(declared) > MAX_REQUEST_BYTES:
                    return None, JSONResponse({"error": "request_too_large"}, status_code=413)
            except ValueError:
                return None, JSONResponse({"error": "invalid_content_length"}, status_code=400)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                return None, JSONResponse({"error": "request_too_large"}, status_code=413)
            body.extend(chunk)
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None, JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(data, dict):
            return None, JSONResponse({"error": "expected_object"}, status_code=400)
        return data, None

    @server.custom_route("/v1/skills/validate", methods=["POST"])
    async def validate_http(request: Request) -> JSONResponse:
        data, error = await _read_authenticated_json(request)
        if error is not None:
            return error
        return JSONResponse(validate_skill(data.get("skill_name"), data.get("skill_md")))

    @server.custom_route("/v1/skills/assess", methods=["POST"])
    async def assess_http(request: Request) -> JSONResponse:
        data, error = await _read_authenticated_json(request)
        if error is not None:
            return error
        return JSONResponse(assess_skill(
            data.get("skill_name"), data.get("skill_md"), data.get("profile", "local")
        ))

    return server


mcp = create_app()
