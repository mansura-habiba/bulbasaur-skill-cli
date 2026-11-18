# Open Agentic Catalog — API-only interoperability example

This is a deliberately read-only integration using real OAC Control API
routes in `api/openapi/control-v1.yaml`:

- `GET /api/v1/capabilities`
- `GET /api/v1/resources?kind=skill&limit=5`

It requires a caller authorized for the local Resource inventory. It is **not**
public ARD Search, a direct publication client, a skill installer, or an
implementation of proposed #76 custom-resource APIs.

```sh
export OAC_API_ORIGIN=http://127.0.0.1:8080
export OAC_BEARER_TOKEN='<scoped-local-token>'
python api/examples/open_agentic_catalog/read_only_client.py
```

The example uses only GET, never follows metadata URLs, and does not send an
assessment to the Catalog. It does not print private Resource content. Use
HTTPS outside loopback. Do not commit tokens.

A proposed integration sequence, **not implemented end-to-end**, would:
(1) obtain an authorized, exact retained Skill representation from Catalog;
(2) confirm its content identity; (3) send the bytes to Bulbasaur's static
assessment API; (4) compare exact digests; (5) retain the result separately
until upstream has accepted a custom Eval/evidence binding.

Candidate Eval and Control definitions are in `api/contracts/`. They are
not registered custom types; the current Catalog governs four built-in kinds.

See `api/docs/open-agentic-catalog-proposal.md` for the detailed scope,
code ownership, acceptance cases, API boundaries, and suggested upstream PRs.
