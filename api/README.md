# Bulbasaur API (FastMCP and HTTP)

The independent `api/` project lives at repository root, **outside**
`bbsctl/src/skillctl/`. The existing skillctl compiler/validator is reused
by `bulbasaur_api.service.SkillAssessmentService`, a transport-neutral Python
API. The CLI and original skillctl code are unchanged.

## Endpoints

| Interface | Address | Behavior |
| --- | --- | --- |
| REST | POST `/v1/skills/validate` | Existing frontmatter validation |
| REST | POST `/v1/skills/assess` | Existing compiler plus static checks |
| MCP | `/mcp`, `validate_agent_skill` | Frontmatter tool |
| MCP | `/mcp`, `assess_agent_skill` | Static compile-assessment tool |
| Health | GET `/healthz` | Unauthenticated health |

Both REST and MCP call the same Python service. Assessment results follow
`contracts/assessment.v1.schema.json`, with SHA-256 of the exact SKILL.md
bytes, findings, profile and explicit `behavioral_evaluation: not_run`.
The assessment runs only the local compile/static steps; it does not invoke
LLMs, third-party scanners or arbitrary scripts. Compile artifacts are written
only to a deleted temporary workspace.

## Run

```sh
cd api
uv sync --extra test
uv run pytest
export BULBASAUR_HTTP_TOKEN=local-development-only-secret
uv run bulbasaur-api
```

Loopback: `http://127.0.0.1:8088`. Example payload for both JSON endpoints:
`{"skill_name":"log-analyzer","skill_md":"---\\nname: log-analyzer\\ndescription: Analyze logs.\\n---\\nBody"}`.
REST requires `Authorization: Bearer local-development-only-secret`.

## OAC #75 / #76 interoperability

Candidate Eval and Control schemas and realistic examples are in
`contracts/`. They are **not** registered Catalog resource kinds or
accepted custom-resource formats. They can be used to discuss the schema
lifecycle in OAC #76 and provide independent test inputs.

OAC #75 is a Go compiled-kind-registry refactor: this project supplies no
replacement for it. The Catalog remains sole authority for resource identity,
version revisions, tenant rights, reviews, releases and discovery.

## Security

Development only; bind to loopback. FastMCP custom HTTP routes do **not**
inherit MCP authentication. REST has its own mandatory bearer token, whereas
the MCP endpoint remains unauthenticated and **must be secured** before
network exposure. HTTP bodies are bounded; MCP tool arguments have no
equivalent transport-level body bound in this prototype and require an
authenticated, size-limited gateway before remote deployment. No arbitrary
host filesystem paths, remote URLs, skill execution or Catalog mutation.
