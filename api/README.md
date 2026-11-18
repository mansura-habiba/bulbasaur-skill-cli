# Bulbasaur API (experimental)

An optional HTTP API **at the repository root**, separate from
`bbsctl/src/skillctl`. The existing `skillctl` Python library is consumed as a
dependency; the CLI and its publishing lifecycle remain unchanged.

## First vertical slice

- `GET /healthz`
- `POST /v1/skills/validate`: accepts JSON with `skill_name` and `skill_md`
- Returns `passed` or `failed`, a SHA-256 of the exact uploaded UTF-8 bytes,
  and bounded structural findings.
- **Only** checks the existing Agent Skills frontmatter rules. Does not compile,
  scan, evaluate, approve, install, publish, or execute a skill.
- Does not offer a caller-selected filesystem path or remote fetch URL.
- No Catalog write operations or direct integration with epic #75/#76 yet.

## Local development

From the repository root (requires Python 3.11–3.13 and uv):

```bash
cd api
uv sync --extra test
uv run pytest
uv run bulbasaur-api
```

The server binds to loopback on port 8088. FastAPI serves OpenAPI at
`http://127.0.0.1:8088/openapi.json` and Swagger UI at `/docs`.

Sample:

```bash
curl -s http://127.0.0.1:8088/v1/skills/validate \
  -H 'content-type: application/json' \
  -d '{"skill_name":"log-analyzer","skill_md":"---\\nname: log-analyzer\\ndescription: Analyze logs.\\n---\\n\\n## Instructions\\nRead logs."}'
```

This service is for isolated local development. Before network exposure, add
request/body limits at the reverse proxy, authentication, rate limiting,
structured error contracts, and explicit resource budgets. The temporary
directory is deleted after parsing, and validation failures do not reflect
uploaded source content.

## Catalog roadmap boundary

Epic #75 (compiled resource kind registry) belongs in Open Agentic Catalog's
Go codebase; this package is **not** a substitute. Epic #76 (custom Eval /
Control / Workflow descriptors) requires an agreed upstream schema contract.
Do not add those as Catalog-native types until that contract is accepted.

Next: extract transport-neutral validation results and add versioned assessment
and descriptor schemas without conflating a Bulbasaur assessment with Catalog
review/approval.
