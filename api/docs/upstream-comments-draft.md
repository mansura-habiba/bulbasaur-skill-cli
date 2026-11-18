# Proposed upstream comments (not posted)

GitHub refused issue-comment creation on
`open-agentic-catalog/open-agentic-catalog` issues #75 and #76 with HTTP 403.
These are review-ready drafts, **not posted comments**.

## #75 — Extensible Resource Kinds

I've been exploring a small API-only compatibility example alongside this
epic, without trying to change the direction of the proposed Go kind registry.

The Bulbasaur branch has a read-only consumer of OAC's existing capabilities
and Skill Resource inventory endpoints, plus offline request-contract tests:

- [Example](../examples/open_agentic_catalog/README.md)
- [Design and ownership boundaries](open-agentic-catalog-proposal.md)

I agree with keeping the actual compiled-kind registry in OAC's Go packages
and preserving the behavior of all four existing kinds.

If useful, I'd be interested in taking a narrowly scoped registry/completeness-
test slice from the existing plan, rather than proposing another abstraction.
Would that fit, or is another part of #75 a better first contribution?

## #76 — Custom Resource Types

I noticed this epic already proposes Eval and Control/Guardrail resource types.
I've built bounded **candidate** JSON Schemas from Bulbasaur's skill evaluation
and guardrail work. They do not introduce a new type registry and are not
claimed to be supported by OAC today:

- [Candidate contracts and examples](../contracts/README.md)
- [API-only OAC example](../examples/open_agentic_catalog/README.md)
- [Detailed design](open-agentic-catalog-proposal.md)

The distinction is intentional: an Eval descriptor is a governed *definition*;
a Bulbasaur assessment result is separate evidence. It never grants Catalog
approval, publication or execution rights.

Would these examples be useful as fixtures when settling #76's schema lifecycle
contract? I'd be happy to adapt to the accepted format and then offer a focused
schema/qualification PR. No request to expand the existing epic's scope.

## Posting status

- #75: NOT POSTED (GitHub connector HTTP 403)
- #76: NOT POSTED (GitHub connector HTTP 403)
- Upstream PRs: NOT OPENED (awaiting maintainer feedback)
