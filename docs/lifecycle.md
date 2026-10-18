# bbsctl lifecycle

The lifecycle (compile → scan → eval → certify → approve → publish) lives **inside** the `bbsctl` binary. There is no second CLI and no product name besides `bbsctl`.

Every stage is a **standalone command**. `bbsctl pipeline` walks them in order and fails fast.

| Stage | Standalone command | Orchestrated by |
|---|---|---|
| new | `bbsctl new` | — (scaffold only) |
| compile | `bbsctl compile` | `bbsctl pipeline` |
| scan | `bbsctl scan` (legacy bbsctl-audit) · `bbsctl inspect` (NVIDIA SkillSpector) | `bbsctl pipeline` |
| eval | `bbsctl eval` | `bbsctl pipeline` |
| certify | `bbsctl mellea-certify` (Mellea) · `bbsctl certify` (config) | `bbsctl pipeline` |
| approve | `bbsctl approve --by <id>` | `bbsctl pipeline` (exit 3 if waiting) |
| publish | `bbsctl publish` | `bbsctl pipeline` (regulated+) |
| — | `bbsctl verify` | after approve |
| — | `bbsctl doctor` | anytime |
| — | `bbsctl publish` | package for install (local / team  / catalog) |
| — | `bbsctl discover` | emit ard.json for ARD discovery |

Config lives in `[tool.bbsctl]` (see `bbsctl/pyproject.toml`). Optional engines that are not on PyPI use the PEP 735 `engines` dependency group so the published wheel stays clean.

## CI (next_move pattern)

Consumer repos follow the same install shape as
[next_move's Bulbasaur workflow](https://github.com/mansura-habiba/next_move/blob/main/.github/workflows/bulbasaur-validation.yml):

1. `actions/checkout` + `setup-python`
2. Clone or install `bbsctl` from this repo (fix hatchling `readme` path)
3. `bbsctl pipeline` / `compile` / `audit` / `eval` against each skill
4. Upload JSON / evidence as an artifact

```yaml
- uses: mansura-habiba/bulbasaur-skill-cli/.github/actions/bbsctl-pipeline@main
  with:
    path: path/to/skill
    strictness: team
    stages: compile
    install-from: clone
```

Or copy `.github/workflows/bbsctl-pipeline.yml` and point `path` at your skills tree.

Local dogfood: `make try-pipeline`.

Recipes: [how each command works](recipes/how-to-commands.md) · [how to run the pipeline](recipes/how-to-run-pipeline.md) · [how to publish](recipes/how-to-publish.md).
