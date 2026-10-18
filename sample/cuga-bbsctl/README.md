# CUGA + bbsctl skill-eval sample

Stage a **skill contract evaluator** for [CUGA](https://github.com/cuga-project/cuga-agent).

CUGA loads `SKILL.md` at runtime (`load_skill`) and has `cuga evaluate` for **agent/API** runs. It does not yet gate skill **folders** (compile / validate / eval corpora). The upstream proposal is a first-class CLI verb:

```bash
cuga skill-eval <skill-name-or-path> [--stage compile|validate|eval|all]
```

That command would depend on optional extra `skill-eval` → PyPI `bbsctl`, and shell out to bbsctl. See [UPSTREAM_DRAFT.md](UPSTREAM_DRAFT.md).

Until that lands in CUGA, this sample mirrors the same stages with Make + a local wheel.

## What this is

- Fixture skill under `fixtures/demo-skill/` (drop into `.cuga/skills` for a live load smoke)
- `make skill-eval` installs the local bbsctl wheel and runs `compile` + `validate`
- Draft for `cuga skill-eval` kept in `UPSTREAM_DRAFT.md` until PyPI

## Commands

```bash
# from repo root
make build
make -C sample/cuga-bbsctl skill-eval
```

Copy into a CUGA checkout:

```bash
mkdir -p /path/to/cuga-agent/.cuga/skills
cp -R fixtures/demo-skill /path/to/cuga-agent/.cuga/skills/demo-skill
```

## After PyPI

1. Publish `bbsctl` to PyPI
2. Open a CUGA PR that adds `cuga skill-eval` + optional extra (from the draft)
3. Point this Makefile at `pip install bbsctl>=x.y.z` instead of the local wheel

Until then, keep work on branch `feature/cuga-bbsctl-eval` only (issue #14). No upstream PR yet.
