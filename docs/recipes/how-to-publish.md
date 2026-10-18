# Recipe: publish a skill

Package a skill so consumers can install it. One verb: **`bbsctl publish`**.

Pair with [`how-to-run-pipeline.md`](how-to-run-pipeline.md) when you need evidence before packaging. Discovery-only (ARD) is **`bbsctl discover`** — see the end of this recipe.

## Prerequisites

- A skill directory with `SKILL.md` (or a catalog artifact folder with `manifest.yml` + `src/`).
- `bbsctl` on your PATH (`uv run bbsctl` from this repo is fine).

Optional: run the lifecycle first so regulated+ paths refuse unsigned evidence:

```bash
bbsctl pipeline --strictness team
bbsctl approve --by alice   # if exit 3
bbsctl verify
```

## Pick a target

| Goal | Command |
|---|---|
| Local Claude marketplace (default) | `bbsctl publish` |
| Team Git marketplace | `bbsctl publish --marketplace ./my-team-marketplace` |
| Catalog curation (in-place, no copy) | `bbsctl publish artifacts/<squad>/<team>/<slug> --inplace` |

`bbsctl marketplace` is admin only (`init` / `list` / `export`). You do not need a `marketplace publish` subcommand.

---

## Path A — local Claude marketplace

From the skill directory:

```bash
bbsctl publish
# → ./bulbasaur-marketplace/  (or --output <dir>)
```

In Claude Code:

```
/plugin marketplace add ./bulbasaur-marketplace
/plugin install <skill-name>-plugin@bulbasaur-local
```

Dry-run without writing:

```bash
bbsctl publish --dry-run
```

---

## Path B — team Git marketplace

Scaffold once, then publish into `plugins/`:

```bash
bbsctl marketplace init ./my-team-marketplace
bbsctl publish ./my-skill --marketplace ./my-team-marketplace
```

Commit and share the marketplace repo. Teammates:

```
/plugin marketplace add <path-or-git-url>
/plugin install <plugin-name>@<marketplace-name>
```

List what is registered:

```bash
bbsctl marketplace list ./my-team-marketplace
```

Bulk catalog → one marketplace (admin):

```bash
bbsctl marketplace export \
  --catalog ./artifacts \
  --marketplace ./my-team-marketplace
```

---

## Path C — catalog curation (in-place)

No file copy. Entries in `.claude-plugin/marketplace.json` point at `./artifacts/.../src`.

Inside the curation repo:

```bash
bbsctl publish artifacts/<squad>/<team>/<slug> --inplace

# Writes / updates:
#   .claude-plugin/marketplace.json
#   artifacts/.../marketplace-entry.json
```

Consumers:

```
/plugin marketplace add <path-or-git-url-of-this-curation-repo>
/plugin install <slug>@<marketplace-name>
```

If you are outside the repo, pass the root explicitly:

```bash
bbsctl publish path/to/artifact --inplace --repo-root /path/to/curation-repo
```

---

## Discover (optional)

Publish makes a skill *installable*. Discover makes it *findable* via [ARD](https://agenticresourcediscovery.org/).

```bash
bbsctl discover ./my-skill --domain example.com -o ard.json
bbsctl discover ./artifacts --catalog --domain example.com

# Or package + emit in one shot
bbsctl publish artifacts/.../slug --inplace --ard
```

Host `ard.json` at `https://<domain>/.well-known/ard.json`. `bbsctl` does not run an ARD search registry.

---

## Checklist

- [ ] Skill compiles (`bbsctl compile` or `bbsctl pipeline --to compile`)
- [ ] Chosen path A / B / C above succeeded without FrameworkError
- [ ] Consumer can `/plugin install …` (or `bbsctl install` for lockfile flows)
- [ ] If regulated+: `bbsctl verify` still green against the published skill hash

## See also

- [`how-to-run-pipeline.md`](how-to-run-pipeline.md) — walk stages before publish
- [`../lifecycle.md`](../lifecycle.md) — stage map and CI action
- [README — Publish vs discover](../../README.md#publish-vs-discover)
