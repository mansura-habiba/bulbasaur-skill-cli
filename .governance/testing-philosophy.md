# Testing philosophy

> The position behind `acceptance.schema.yaml`. Read once, then let CI do the enforcing.

---

## The core position

**AI can write tests. AI must not write the specification the tests are written against.**

When AI writes both the spec (in markdown) and the test (in pytest), it satisfies its own vague prose. The tests pass. The code is wrong. The reviewer can't tell, because everything aligns internally — the AI has talked itself into coherence with no external check.

The fix is **separation of authoring authority**:

| Artifact | Who authors | Format |
|---|---|---|
| `acceptance.yaml` (the spec) | Human (lead, senior, architect) | Structured YAML, schema-validated |
| `tests/contract/*.py` (the test code) | Allowed: AI, junior, senior — anyone | Python, references case_id |
| Markdown describing intent | Human, optionally AI-drafted | Prose, **never** the source of truth |

When the spec is structured and human-authored, AI cannot drift it. When the tests reference `case_id` from the spec, AI cannot invent assertions that please the code. When the contract test suite validates that every assertion traces to a case_id, AI cannot smuggle in tautologies.

---

## Why markdown fails as a spec layer

Markdown was designed for human reading. Three failure modes when it's used as a test spec:

**1. Ambiguity is invisible.** A markdown bullet says "validates the skill correctly." The AI implementing the test decides what "correctly" means. The reviewer skims it. Six months later, a junior changes the validator, the test still passes, and the meaning of "correctly" has silently shifted. Schemas don't have this failure mode — `kind: positive` plus `then.outcome: returns` plus a typed `then.value` is unambiguous in a way prose cannot be.

**2. AI-generated markdown looks authoritative.** AI is excellent at producing fluent, structured-looking markdown that's wrong. The fluency is the problem — humans pattern-match on competence, not correctness. A 200-word "definition of done" written by AI reads as authoritative because it sounds like every other definition of done the human has seen. Structured YAML doesn't trigger the same pattern-matching. A missing field in a YAML schema is mechanically visible; a missing concept in a paragraph is not.

**3. Markdown specs cannot be linted.** You can run JSON Schema validation on a YAML. You can run mutation testing on a Python file. You cannot run anything meaningful on a markdown paragraph — at best you can grep it for keywords, which is exactly the kind of fragile check AI immediately learns to satisfy.

This is the same lesson as MDD (model-driven development): code-from-spec works in domains where the spec lives at a stable, parseable abstraction layer. Markdown isn't that layer. Structured YAML is.

---

## The anti-patterns this framework targets

Each row of the table maps to a guard in `acceptance.schema.yaml` or `tests/contract/test_acceptance_validates.py`. None of this is theory; it's all enforced.

| Anti-pattern | What it looks like | Guard |
|---|---|---|
| **Tests that please the code** | Assertions extracted by reading the implementation, not the spec. | `test_quality_gates.no_implementation_strings_in_assertions`; mutation testing |
| **Tests that mock the unit under test** | `mock.patch("module.function_under_test")` then asserts it was called. | `test_quality_gates.no_mocking_of_unit_under_test` |
| **Coverage chasing** | Tests added to hit a coverage threshold, asserting nothing useful. | `test_quality_gates.coverage_must_be_intentional` + assertion-to-case_id linkage |
| **Tautological tests** | `assert foo() == foo()` or "test returns what the function returns." | Mutation testing — score collapses if tests are tautological |
| **Happy-path-only specs** | Acceptance spec with no `kind: negative` cases. | Validator rejects ratified specs missing negative coverage |
| **Orphan assertions** | Test assertions that don't trace to any case in the acceptance spec. | `test_no_orphan_assertions_in_contract_tests` lint |
| **AI-authored spec** | The acceptance spec itself was generated. | `authored_by.ai_assistance` field, defaults to `forbidden`. Human signs. |
| **Pleased-by-the-name tests** | `def test_validates_correctly():` with no body that proves anything. | Mutation score; review focused on intent, not coverage |
| **Spec rot** | Spec drifts away from tests over time. | Every case has `evidence.test_id` that CI verifies resolves |
| **The "trust me, I tested it" PR** | No test linked, manual verification claimed. | PR template requires test output paste; CI checks contract tests pass |

---

## What we recommend beyond schema validation

Schema validation catches structural problems. The hard ones are semantic — tests that pass but prove nothing. Three techniques you should add, in order of payoff:

### 1. Mutation testing

Mutation testing introduces small changes to the production code (e.g. flipping `>` to `>=`) and re-runs the test suite. If the tests still pass, they don't actually test that line. Mutation score = fraction of mutants caught. Below 0.7 your tests are scenery; above 0.85 they're load-bearing.

Tools: `mutmut` (Python), `Stryker` (JS), `pitest` (Java). Run on a schedule (nightly or per release), not per PR — it's slow.

This is the single most effective defense against AI-generated tests that please the code, because a mutation-killing test can only exist if the assertion is grounded in the spec, not in the implementation.

### 2. Property-based testing

Example-based tests (the cases in `acceptance.yaml`) prove specific points. Property-based tests prove ranges. "For any valid skill ID, validation is idempotent" is a property — Hypothesis (Python) or fast-check (JS) generates thousands of inputs to try to falsify it.

Properties are also harder for AI to "please." There's no specific input string to grep; the AI has to write code that actually implements the property, or the test fails on inputs it didn't anticipate.

Use the `invariants` section of the acceptance spec for these.

### 3. Contract-as-fixture, not contract-as-prose

When a contract test asserts behavior at a boundary (HTTP API, function signature, message format), the expected payload should be a fixture file, not an inline literal. Fixtures are versioned alongside the contract; PRs that change them are visible diffs. Inline literals get edited by AI silently.

Example: instead of `assert response.json() == {"status": "rejected", "code": "AGS-001"}`, write `assert response.json() == json.loads(fixture("rejected-missing-name.json"))` and check the fixture into `tests/fixtures/`. Now the contract is a file the reviewer can diff.

---

## The reviewer's job (under this framework)

When the framework is working:

- **Schema validation, contract tests, mutation score, coverage** — all CI's job. The reviewer does not check any of these.
- **Architectural fit** — does this PR cohere with the wider direction in `goal.bigger_picture`?
- **Choice of abstraction** — is this the right level of indirection?
- **Edge cases the spec missed** — did the author cover the ground that wasn't anticipated when the spec was authored? If they spotted a gap, did they file a follow-up to extend the spec?
- **Business correctness** — does this behavior match what the user actually needs?

If you find yourself reviewing a PR for whether the tests follow conventions, the framework is misconfigured — add a check, don't repeat the review.

---

## When to permit AI-drafted acceptance specs

The default in the schema is `authored_by.ai_assistance: forbidden`. There is one exception that's reasonable: **a senior asks AI to draft a strawman, then extensively edits it.** This is `draft_only` — the value is documenting that AI touched the spec at all, not whether the touch was approved.

What's never permitted:
- AI writing the spec because "the human will review it" — review of generated specs has the same fluency-vs-correctness failure as review of generated tests.
- AI updating an existing spec without a paired human-authored ADR explaining the change.
- AI authoring the `forbidden_behaviors` list — the things the system must never do are the things a human must understand well enough to enumerate.

---

## The honest test for whether this is working

Run this experiment in three months: pick five acceptance specs, delete the contract tests, hand the spec to a different AI assistant (or a junior unfamiliar with the area) and ask them to author the tests from scratch. Compare the resulting tests to the originals.

If the new tests look substantially the same: the spec is doing its job — it constrains the test space tightly enough that any conforming test passes the same checks.

If the new tests look different: the spec is too loose. Strengthen `assertions[]`, `must_not[]`, and `forbidden_implementations[]` until two independent implementers produce equivalent tests.

This is the spec-driven version of "does my test prove what I think it proves." Mutation testing answers the same question mechanically. Run both.
