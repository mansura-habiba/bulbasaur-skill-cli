# API-first integration implementation checklist

This is a **current implementation ledger**, not a claim that upstream OAC
epics are complete. The independent Bulbasaur changes are in draft PR #26.

| Work item | State | Evidence |
| --- | --- | --- |
| Extract Python API | Implemented | `api/src/bulbasaur_api/service.py` |
| Version contracts | Implemented | `api/contracts/assessment.v1.schema.json` |
| Eval and Control descriptors | Candidate schemas + fixtures implemented | `api/contracts/*resource*.schema.json` |
| Add HTTP transport | Implemented (local only) | `api/src/bulbasaur_api/app.py` FastMCP and HTTP |
| Interoperability tests | Offline contract tests implemented | `api/tests/test_oac_example.py` |
| Upstream contribution | Prepared, **not submitted** | `api/docs/open-agentic-catalog-proposal.md` |

## Explicitly pending upstream

OAC issue #75 owns the Go compiled-kind registry implementation. OAC issue
#76 owns the administrator-configured type lifecycle. Neither is implemented
by the Bulbasaur Python API. Submit focused Go and schema/fixture PRs only
after the OAC maintainer confirms scope and review expectations.

## Verification

The API GitHub Actions workflow runs `uv sync --extra test && uv run pytest`.
The offline Catalog example does **not** prove integration with a live Catalog.
Never describe static assessment success as Catalog approval or as proof that
an agent skill is safe to execute.

## Access and isolation

The HTTP endpoint requires its own bearer token. The MCP transport remains
unauthenticated in this local prototype. Keep the process on loopback until
separately reviewed authentication and request limits exist for both surfaces.
