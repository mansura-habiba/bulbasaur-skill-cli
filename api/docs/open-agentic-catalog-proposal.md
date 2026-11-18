# Candidate API interoperability for Open Agentic Catalog #75 and #76

**Status:** Independent exploratory design, not accepted by the OAC maintainer.
**Audience:** Mihai, maintainers, reviewers and coding agents.
**Primary rule:** OAC governs metadata; Bulbasaur assesses skills. Do not
merge their approval, execution or persistence authority.

## Objective and overlap

OAC #75 proposes a compiled Go registry reducing repeated kind dispatch and
an initial descriptor-only kind. OAC #76 proposes tenant-configured resource
definitions with Eval, Control and Workflow examples and bounded JSON Schema
validation. These upstream epics **already** set the architecture direction.

Bulbasaur currently owns Agent Skills parsing, a compile pipeline, static
checks, optional evaluators, artifact evidence and local marketplace tooling.
The top-level `api/` exposes reusable static assessment through a Python
service and two transports: FastMCP tools and custom JSON HTTP routes. It
does **not** install or publish resources through OAC.

## Ownership boundary

| Responsibility | OAC | Bulbasaur |
| --- | --- | --- |
| Resource/VersionRevision/Listing identity | Owns | Does not replace |
| Tenant permission, review, release, publication | Owns | Never grants |
| Native Skill schema validation | Owns | Independently parses SKILL.md |
| Candidate Eval/Control definitions | May govern under #76 | Produces examples |
| Runtime assessment | Does not execute | Owns local assessment |
| Assessment report | May reference only via agreed contract | Produces result + digest |
| Execution/installation | Neither in this integration | Not invoked via API |

A digest of supplied SKILL.md alone does not authenticate the publisher or
identify the digest of an entire Skill package. A self-described evaluation
result does not establish correctness, safety or Catalog approval.

## Implemented Bulbasaur components

- `api/src/bulbasaur_api/service.py`: transport-neutral
  `SkillAssessmentService.validate()` and `assess()`.
- `api/src/bulbasaur_api/app.py`: FastMCP with MCP tools and JSON routes.
- `api/contracts/assessment.v1.schema.json`: static assessment output.
- `api/contracts/eval-resource.v1.schema.json`: candidate custom Eval.
- `api/contracts/control-resource.v1.schema.json`: candidate custom Control.
- `api/contracts/examples/`: reproducible small resource definitions.
- `api/examples/open_agentic_catalog/`: actual API-only, read-only client.
- `api/tests/`: schema, service, transport and OAC request contract checks.

No CLI, custom resource administration, OAC schema install, or Catalog data
mutation is required for the implemented example.

## Existing OAC endpoints used

`GET /api/v1/capabilities` and
`GET /api/v1/resources?kind=skill&limit=5` are present in OAC's
`api/openapi/control-v1.yaml`. The second is an authorized **local Resource
inventory**, not a published ARD search. It requires current Catalog access.
The example uses only GET and does not follow URLs from metadata.

A later end-to-end Skill assessment consumer would need an explicitly
selected exact representation read, checked against authoritative content
identity. We have **not implemented that end-to-end flow**, and no unsupported
or guessed OAC endpoint is used.

## Epic #75: specific code contribution

The proposed compiled-kind registry belongs **in OAC's Go repository**, not
in Bulbasaur's Python. The upstream issue identifies:

- `internal/catalog/types.go`: kind enum
- `internal/adapter/registry.go`: native validation routing
- `internal/publication/manager.go`: publication mapping
- `internal/federation/manager.go`: media-type-to-kind mapping
- DB CHECK constraints, OpenAPI enum, SDKs, UI: additional explicit admission

Desired first PR: a *four-existing-kind* registry and completeness tests,
without adding new public kinds or changing response semantics. Acceptance:
native validators, existing searches, publication, federation, permissions,
API contracts and client behavior remain unchanged. An incomplete definition
fails a focused completeness test. No automatic SQL/SDK/schema mutation.

Bulbasaur contributes a real client compatibility fixture (read-only
capabilities and Skill inventory) but does not itself implement Go refactoring.

## Epic #76: candidate contract contribution

The proposed Eval descriptor contains `schemaVersion`, `name`,
`target.resourceIdentifier`, `target.version`, and bounded `cases`
with `id`, `input` and `expectedBehavior`. The Control descriptor
contains `schemaVersion`, `name`, `subject` and bounded declarative
`rules`. Neither descriptor executes anything. Both reject unknown top-level
properties. They are independent JSON objects suitable for *discussion* under
#76's admin-configured format model.

OAC must still agree type-definition authority, immutable schema binding,
media types, finite parser budgets, discovery representation, lifecycle
eligibility and access controls. JSON Schema passing locally does not imply
OAC can already admit the document.

## Security and operational controls

- HTTP custom routes have independent bearer authentication because FastMCP
  custom routes do not inherit MCP authentication.
- MCP has no remote authentication in this MVP, so bind to loopback only.
- HTTP bodies and SKILL.md bytes are bounded. MCP tool argument budgets need
  an authenticated limiting layer before remote use.
- No arbitrary remote input URL or caller-selected server filesystem path.
- Existing compiler writes `dist/` only under an automatically discarded
  temporary workspace.
- No runtime evaluation, scripts, secret exfiltration tests or external model
  calls are executed by this static assessment endpoint.
- Do not treat `passed` as Catalog review, approval or publication.
- The local OAC API example requires HTTPS except for loopback and does not
  follow untrusted metadata links.
- Current OAC tenant isolation, authorization on replay and immutable history
  must remain unchanged in any future PR.

## Verification and gaps

| Claim | Test location | Status |
| --- | --- | --- |
| Static assessment and result schema | `api/tests/test_api.py` | Automated |
| Invalid and oversized input refusal | `api/tests/test_api.py` | Automated |
| MCP tool discovery + HTTP bearer guard | `api/tests/test_api.py` | Automated |
| Eval/Control candidate schema validation | `api/tests/test_api.py` | Automated |
| OAC read-only request shape | `api/tests/test_oac_example.py` | Mocked offline |
| Real authenticated OAC integration | not run | Pending owned local Catalog |
| OAC #75 native Go refactor | upstream repository | Not implemented here |
| OAC #76 custom-kind lifecycle | upstream repository | Pending design acceptance |
| Model-based security/eval effectiveness | not part of static service | Not claimed |

The API tests and CI results should be linked with their commit SHA when
reporting outcomes. Offline mocked requests do not prove live interoperability.

## Proposed contribution strategy

1. Request review of this document and the candidate contracts *before*
   implementing upstream behavior.
2. Offer a small OAC #75 Go completeness-test/refactor slice under the
   existing epic, with unchanged four-kind behavior.
3. Offer the Eval/Control schema examples and focused validation cases for
   #76 after the type definition contract is accepted.
4. Only after both agree, test an exact OAC Skill representation read ->
   separately authorized Bulbasaur assess -> independently verified digest.
5. Keep external assessment/evidence import and runtime integration out of
   both initial epic PRs.

## Instructions for coding agents

Read OAC `DESIGN.md`, `CONTRIBUTING.md`, issues #75 and #76 and accepted
ADRs. Upstream decisions override candidate choices in this document.
Never create OAC APIs by inference; verify each route in the current pinned
OpenAPI contract. Keep governed lifecycle steps separate. Do not edit applied
migrations, assume permissions, infer verified trust from publisher prose, or
publish based on Bulbasaur's own success status. Use synthetic fixtures and
report actual tests separately from intended future behavior.
