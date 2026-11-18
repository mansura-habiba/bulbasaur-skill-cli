# Candidate Bulbasaur / OAC #76 contracts

These JSON Schemas are versioned local candidate descriptors and **not**
approved Open Agentic Catalog resource definitions or registered media types.

- `assessment.v1.schema.json`: static assessment response; independent of any
  governance approval, and always marks behavioral evaluation as `not_run`.
- `eval-resource.v1.schema.json`: bounded Eval definition, with no model execution.
- `control-resource.v1.schema.json`: declarative guardrail/control metadata,
  with no policy enforcement.

The Catalog owns custom type identity, administration, admission, review,
release, publication and media-type mapping. This directory provides examples
and independent consumer fixtures for discussing issue #76. It is not a
schema-registration API, and no direct Catalog mutation occurs.

For issue #75, the Catalog's reviewed compiled Go kind registry is the relevant
implementation. These schemas should not be represented as native Go kinds.
