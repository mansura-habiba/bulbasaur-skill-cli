# Bulbasaur API: integration guide and design

**Status:** Experimental implementation in the `feat/top-level-assessment-api` branch.  
**Audience:** API consumers, catalog maintainers, application developers, and coding agents.

Bulbasaur offers reusable, versioned skill-validation and static-assessment
operations. Applications, registries, and catalogs can invoke the same
operations using a Python library, JSON over HTTP, or Model Context Protocol
(MCP). No catalog-specific plugin, CLI invocation, or schema registration is
required to call the API.

## How the API works

```text
Catalog / application / agent
          |
          +-- HTTP POST /v1/skills/validate
          +-- HTTP POST /v1/skills/assess
          +-- MCP validate_agent_skill
          +-- MCP assess_agent_skill
          |
          v
   FastMCP transport (api/)
          |
          v
 SkillAssessmentService (api/)
          |
          v
 Existing skillctl parsing / compilation / static rules
          |
          v
 Structured result with findings and SKILL.md SHA-256
```

The API lives under repository-root `api/`, separate from the
`bbsctl/src/skillctl/` package. `skillctl` provides the existing Agent
Skills parser and compiler. The API's service object supplies a transport-
independent entry point; the HTTP and MCP handlers call that same service.
Existing CLI behavior is unchanged.

The current API accepts the text of **one SKILL.md**, not an arbitrary
Skill package or remote URL. The SHA-256 identifies exactly those uploaded
UTF-8 bytes; it is not a package hash, signature, or publisher attestation.

## Available operations

| Operation | Interface | Behavior |
| --- | --- | --- |
| Validate | `POST /v1/skills/validate` | Agent Skills frontmatter and required-field checks |
| Assess | `POST /v1/skills/assess` | Existing compile pipeline and static steps |
| Validate | MCP tool `validate_agent_skill` | Same validation function as HTTP |
| Assess | MCP tool `assess_agent_skill` | Same static assessment function as HTTP |
| Health | `GET /healthz` | Minimal service health response |

The MCP endpoint is served at `/mcp` using FastMCP Streamable HTTP. FastMCP
is the server framework; no FastAPI, Swagger UI, or OpenAPI publication is
necessary to call these operations.

### JSON request

```json
{
  "skill_name": "log-analyzer",
  "skill_md": "---\nname: log-analyzer\ndescription: Analyze log entries and identify errors.\n---\n\n## Instructions\nRead the supplied logs without modifying files.",
  "profile": "local"
}
```

`profile` is optional for `/v1/skills/assess` (default: `local`).
The validation endpoint ignores profile because it performs frontmatter
validation only. MCP tools accept the corresponding named arguments.

### Assessment response

```json
{
  "schema_version": "bulbasaur.assessment/v1",
  "status": "passed",
  "artifact": {
    "media_type": "text/markdown",
    "sha256": "<64 hexadecimal characters>"
  },
  "assessment": {
    "profile": "local",
    "mode": "static",
    "checks_run": 4
  },
  "findings": [],
  "behavioral_evaluation": "not_run",
  "catalog_approval": "not_applicable"
}
```

This example is illustrative: the digest and number of checks must be
taken from an actual run. The normative result schema is
`api/contracts/assessment.v1.schema.json`. Validation uses the smaller,
backward-compatible `status`, `artifact_sha256`, `validator`, `findings`
response shape.

`passed` means the invoked checks passed. It does not indicate
behavioral evaluation, security certification, approval, or permission to
execute. Assessment runs static compile steps in a temporary workspace and
removes the workspace afterward.

## Local startup and requests

From the repository root:

```sh
cd api
uv sync --extra test
uv run pytest -q
export BULBASAUR_HTTP_TOKEN='local-development-secret'
uv run bulbasaur-api
```

The development service binds to `127.0.0.1:8088`. For REST, supply
`Authorization: Bearer local-development-secret`. For example:

```sh
curl -sS http://127.0.0.1:8088/v1/skills/assess \
  -H 'Authorization: Bearer local-development-secret' \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

A Python consumer can call the transport-neutral service without starting
the server:

```python
from bulbasaur_api.service import SkillAssessmentService

result = SkillAssessmentService().assess(
    skill_name="log-analyzer",
    skill_md=skill_markdown,
    profile="local",
)
```

### What any catalog needs to integrate

1. Read an **exact selected skill revision** using the catalog's existing
   authenticated read mechanism. Obtain the actual SKILL.md bytes rather than
   relying on a description or search snippet.
2. Call Bulbasaur `/v1/skills/validate` or `/v1/skills/assess`, or the
   corresponding MCP tool, with the skill name and document text.
3. Validate the result against the versioned contract. Verify the returned
   SKILL.md digest against independently retained bytes or evidence.
4. Display or retain the findings as external assessment information.
   Decide how to bind or publish such evidence **using that catalog's own
   governance and API contract**. The Bulbasaur API does not automatically
   mutate any catalog.

A catalog may be implemented in Go, Python, Java, TypeScript, or another
language: interoperability requires only JSON HTTP or MCP support. The API
does not assume any particular catalog's resource, release, or approval model.

## Extensible descriptors

The `api/contracts/` directory also includes **candidate** JSON Schema
definitions for Eval and Control descriptions, with real examples. These
are portable metadata proposals, not runtime engines and not registered
resource kinds in any external catalog.

- `eval-resource.v1.schema.json`: evaluation definition, target and bounded
  cases; does not run the cases.
- `control-resource.v1.schema.json`: subject and declared control rules;
  does not enforce the rules.
- `examples/`: small sample documents for consumer-side schema testing.

A catalog that supports custom JSON resource types could *choose* to admit
these descriptions through its normal type-definition lifecycle, but the
Bulbasaur API does not require it.

## Security and operational boundaries

- HTTP routes created with FastMCP `custom_route` do **not** inherit
  FastMCP MCP authentication. The REST endpoints therefore require a
  separate `BULBASAUR_HTTP_TOKEN`.
- The MCP endpoint is **unauthenticated in this development implementation**.
  Keep the service loopback-only. Add MCP authentication and transport-level
  request limits before remote deployment.
- HTTP bodies and SKILL.md inputs are bounded. No arbitrary file path, URL
  fetch, installation, external scanner, script execution, or model-based
  evaluation is exposed by these endpoints.
- A document digest alone proves neither source authenticity nor safety.
  Treat submitted skill content as untrusted data.
- Parser error details are not echoed to clients. Generated compilation
  artifacts are written only in an automatically deleted temporary workspace.

## Open Agentic Catalog example (one integration)

The runnable, read-only OAC example is in
`api/examples/open_agentic_catalog/`. It calls the **existing** Control API
routes `GET /api/v1/capabilities` and
`GET /api/v1/resources?kind=skill&limit=5`. The latter is an authorized
local Resource inventory, not public ARD Search.

That example demonstrates API access and request boundaries. It **does not**
yet fetch an exact Skill representation and submit it to Bulbasaur, so it
must not be called a live end-to-end integration.

For potential upstream contributions:

- [OAC issue #75](https://github.com/open-agentic-catalog/open-agentic-catalog/issues/75)
  proposes an internal compiled Go resource-kind registry. The Python API
  does not implement that change.
- [OAC issue #76](https://github.com/open-agentic-catalog/open-agentic-catalog/issues/76)
  proposes custom Eval, Control, and Workflow resource types. Bulbasaur's
  candidate descriptor schemas may help as example inputs, subject to the
  OAC maintainer's contract decisions.

These are **optional compatibility opportunities**; OAC-specific behavior
is not embedded into the Bulbasaur service layer.

## Verification and current limits

| Capability | Evidence | Scope |
| --- | --- | --- |
| Validation and static assessment | `api/tests/test_api.py` | Automated |
| REST bearer check and request limits | `api/tests/test_api.py` | Local HTTP test |
| MCP tool registration and call | `api/tests/test_api.py` | In-process MCP test |
| Assessment response JSON Schema | `api/tests/test_api.py` | Automated |
| Eval/Control example validity | `api/tests/test_api.py` | Automated candidate schemas |
| OAC read-only request shape | `api/tests/test_oac_example.py` | Mocked offline |
| Real catalog-to-assessment flow | Not implemented | Future integration |
| External network security qualification | Not performed | Development-only |

To extend this integration, add independent, scoped tests for the exact
catalog-specific read contract and actual resulting bytes. Do not invent
API routes or infer publication privileges. Keep fixture expectations
separate from verified live consumer results.

## Notes for maintainers and coding agents

Start with `api/src/bulbasaur_api/service.py`,
`api/src/bulbasaur_api/app.py`, `api/contracts/`, and `api/tests/`.
Keep transport-specific code in `api/` and keep `skillctl` reusable.
Version public response schemas deliberately and preserve compatibility.
Do not turn a static assessment success into approval, execution
authorization, or a cross-catalog publication decision.
