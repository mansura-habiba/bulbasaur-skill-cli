# Bulbasaur FastMCP API (experimental)

Lives in repository-root `api/`, outside `bbsctl/src/skillctl`.
One FastMCP process provides both an MCP tool and a JSON HTTP endpoint,
reusing the existing `skillctl` parser. No FastAPI, Swagger UI, or required
OpenAPI endpoint. CLI behavior is unchanged.

| Interface | Endpoint | Notes |
| --- | --- | --- |
| MCP | `/mcp`, tool `validate_agent_skill` | Tool discovery and call |
| HTTP | `POST /v1/skills/validate` | JSON request and result |
| Health | `GET /healthz` | Unauthenticated |

## Local run

```bash
cd api
uv sync --extra test
uv run pytest -q
export BULBASAUR_HTTP_TOKEN=local-development-only-secret
uv run bulbasaur-api
```

The service listens on 127.0.0.1:8088. Call REST with JSON
`{"skill_name":"log-analyzer","skill_md":"---\\nname: log-analyzer\\ndescription: Analyze logs.\\n---\\nBody"}`
and `Authorization: Bearer local-development-only-secret`.

## Security boundaries

**Local development only; do not expose externally.** FastMCP custom routes
bypass its MCP authentication, so REST has a separate mandatory bearer token.
MCP is currently unauthenticated and must be secured before remote deployment.
REST inputs are bounded and uploaded text is not executed. Validation only
checks structural frontmatter and does not mean safety, approval, certification,
execution, installation, or publication. Digest is for SKILL.md bytes only.

Open Agentic Catalog #75 remains a Go registry implementation. #76 requires
agreed Eval and Control resource contracts; these are not yet implemented.
