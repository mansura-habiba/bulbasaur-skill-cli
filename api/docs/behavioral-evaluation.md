# Opt-in behavioral evaluation — request and operator configuration

The default `POST /v1/skills/assess` and MCP `assess_agent_skill`
continue to perform static checks and report
`"behavioral_evaluation": "not_run"` (v1 response).

When a caller explicitly supplies `evaluation.enabled=true` with valid inline
cases, Bulbasaur runs the existing `skillctl.eval.EvalRunner` and returns
`bulbasaur.assessment/v2` with a structured behavioral result.

## Example request

See `api/examples/behavioral-evaluation/request.json` for a complete request:

```json
{
  "skill_name": "reply-helper",
  "skill_md": "---\nname: reply-helper\ndescription: Respond with a fixed greeting when asked.\n---\n\n## Instructions\nReply with: \"Hello there\"\n",
  "evaluation": {
    "enabled": true,
    "runtime": "mock",
    "judge": "heuristic",
    "threshold": 1.0,
    "cases": [{
      "id": "greeting-1",
      "prompt": "Greet the user",
      "expected_output": "Hello there",
      "assertions": ["Hello there"]
    }]
  }
}
```

The request is the same through REST or MCP. The `mock` backend invokes the
actual deterministic `MockAgent` from `skillctl`; this **tests plumbing and
assertion scoring**, not whether a real LLM agent follows a skill.

## Operator configuration

Set `BULBASAUR_EVAL_CONFIG` on the server to the path of a trusted local
JSON file, e.g. `operator-config.json`. It is **not** accepted from API callers.

```json
{
  "allowed_runtimes": ["mock"],
  "max_cases": 12,
  "enable_real_runtimes": false
}
```

Default (no file): only `mock` is allowed. To enable an existing real backend
such as `ollama`, an operator must allowlist it and explicitly set
`enable_real_runtimes` to true. This is **not a production-ready isolation
mechanism**: live model calls may transmit untrusted case text and there is
no hard wall-clock run deadline. Do not enable real runtimes in a remotely
accessible deployment without a proper worker sandbox, network egress policy,
timeouts, resource budgets and per-tenant authorization. Only `heuristic`
judging is currently admitted by the API.

API calls cannot choose a server filesystem path, runtime model endpoint,
shell command, or user-supplied operator policy. Cases are bounded by count,
prompt/expected length and assertion length. Evaluation only runs when static
compilation passes. A missing/empty case set is refused rather than passing
vacuously. Output excludes prompts, model replies and judge reasons to reduce
sensitive-data disclosure.

## Evidence interpretation

Results report `status`, `runtime`, `judge`, `mode`, `cases_run`,
`cases_passed`, `score`, `corpus_sha256` and per-case pass/score/error.
`mode=deterministic_mock` must never be described as an LLM behavioral
certification. The score is a heuristic-judge estimate, not objective task
quality. `catalog_approval` remains `not_applicable`. Schema v1 stays
unchanged for static-only clients; opt-in evaluation uses the v2 contract.

## Future harness support

Pi or Gantry should be added behind a deliberately reviewed harness adapter,
not via arbitrary runtime names supplied over HTTP. A real evaluator should
be run asynchronously in a bounded isolated worker with explicit cancellation,
per-run model/version evidence, tool permissions and outcome-based assertions.
