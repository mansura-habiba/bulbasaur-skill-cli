# Langflow + bbsctl sample

Wire Langflow ChatInput through a custom component that shells out to the public
`bbsctl` CLI (`compile`, `validate`, or `eval`), then routes to Pass or Fail ChatOutput.

## Layout

- `components/skill_eval/` — domain types and the Langflow component
- `flows/BbsctlSkillEval.json` — minimal flow graph (ChatInput → eval → Pass/Fail ChatOutput)
- `fixtures/example-skill/` — skill directory for smoke compile/validate
- `wheels/` — local `bbsctl` wheel copied by `make wheel` (gitignored `*.whl`)

## Commands

```bash
# Copy bbsctl wheel from ../../bbsctl/dist into wheels/
make wheel

# Unit tests (stubs Langflow; no Docker required)
make test

# Build and run Langflow on http://localhost:7860
make docker-build
make docker-up
```

## Flow wiring

Import `flows/BbsctlSkillEval.json` in Langflow, or rebuild by hand.

1. ChatInput → `BbsctlSkillEval` (`skill_dir`, `stage`, `timeout_sec`)
2. `pass_result` → ChatOutput (Pass)
3. `fail_result` → ChatOutput (Fail)

The component runs `bbsctl <stage> <skill_dir>`. If `bbsctl` is missing from
`PATH`, it falls back to `python -m skillctl`.

## Docker notes

The Dockerfile installs public `langflow` from PyPI and the local wheel under
`wheels/`. Run `make wheel` before `make docker-build`.

If `docker` is not on `PATH`, or `docker build` fails with network errors in a
restricted environment, leave the image unbuilt. The Dockerfile and
`docker-compose.yml` stay ready for a host with Docker and PyPI access.

