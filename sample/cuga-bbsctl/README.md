# CUGA + bbsctl skill-eval sample

Stage a **skill contract evaluator** workflow for [CUGA](https://github.com/cuga-project/cuga-agent).

CUGA already loads `SKILL.md` at runtime (`load_skill`). It also has `cuga evaluate` for **agent/API** test cases. It does **not** run bbsctl-style compile / validate / eval corpora against skill folders. This sample fills that gap as a local Make gate.

## What this is

- Fixture skill under `fixtures/demo-skill/` shaped for CUGA’s default `.cuga/skills` layout
- `make skill-eval` installs the local bbsctl wheel and runs `compile` + `validate` (+ optional `eval`)
- Draft snippets for a future CUGA upstream PR (optional extra + docs), kept here until PyPI

## Commands

```bash
# from repo root
make build
make -C sample/cuga-bbsctl skill-eval
```

Copy the fixture into a CUGA checkout when you want a live load smoke:

```bash
mkdir -p /path/to/cuga-agent/.cuga/skills
cp -R fixtures/demo-skill /path/to/cuga-agent/.cuga/skills/demo-skill
# in CUGA: skills.root = cuga (default), then restart / cuga start …
```

## After PyPI

1. Publish `bbsctl` to PyPI
2. Open a CUGA PR from [UPSTREAM_DRAFT.md](UPSTREAM_DRAFT.md) (optional `skill-eval` extra + Agent skills docs)
3. Point this Makefile at `pip install bbsctl>=x.y.z` instead of the local wheel

Until then, keep work on branch `feature/cuga-bbsctl-eval` only (issue #14). No upstream PR yet.
