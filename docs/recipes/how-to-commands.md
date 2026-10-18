# Recipe: what each `bbsctl` command does

One binary: **`bbsctl`**. Lifecycle stages are also standalone commands; `bbsctl pipeline` walks them in order.

**Inspect vs scan:** use **`bbsctl inspect`** for NVIDIA **[SkillSpector](https://github.com/NVIDIA/SkillSpector)**. **`bbsctl scan`** is the legacy lightweight path (`bbsctl-audit`).

Related recipes: [run the pipeline](how-to-run-pipeline.md) · [publish](how-to-publish.md) · [lifecycle map](../lifecycle.md).

---

## Quick map

| Command | Job | Who actually runs it |
|---|---|---|
| `bbsctl new` | Scaffold `SKILL.md` | bbsctl (in-process) |
| `bbsctl compile` | Structural parse + report | bbsctl |
| `bbsctl validate` | Fast / full validators | bbsctl |
| `bbsctl inspect` | Security inspection → SARIF | **[NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector)** |
| `bbsctl scan` | Legacy lightweight scan | `bbsctl-audit` (built-in) |
| `bbsctl eval` | Behavioural corpus | bbsctl + runtime/judge adapters |
| `bbsctl mellea-certify` | Risk certify / policy artifacts | **[Mellea](https://github.com/generative-computing/mellea-skills-compiler)** |
| `bbsctl certify` | Certify stage (config-driven) | `mellea` or `none` per `[tool.bbsctl.engines]` |
| `bbsctl approve` | Human sign-off on evidence | human (writes `approval.json`) |
| `bbsctl verify` | Re-check digests / approval | bbsctl |
| `bbsctl publish` | Package for install | bbsctl (+ marketplace / catalog layout) |
| `bbsctl discover` | Emit `ard.json` | bbsctl (ARD emit only) |
| `bbsctl pipeline` | Walk stages fail-fast | orchestrates the engines above |
| `bbsctl doctor` | Which engines are on PATH | bbsctl |
| `bbsctl run` | Activate skill once | mock / ollama / claude-agent-sdk |
| `bbsctl audit` | Trust audit of a skill tree | bbsctl |
| `bbsctl fetch` | Download external skill + audit | bbsctl |
| `bbsctl marketplace …` | Admin: init / list / export | bbsctl |
| `bbsctl risk` | Print strictness × risk matrix | bbsctl (docs/matrix; not SkillSpector) |

Engine choice lives in `[tool.bbsctl]` (see `bbsctl/pyproject.toml`). Check with:

```bash
bbsctl doctor
```

---

## Inspect (NVIDIA SkillSpector)

`bbsctl inspect` always runs **[NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector)** — it does not implement deep static analysis in-process. The adapter shells out to the `skillspector` CLI and normalises SARIF into a `StageResult`.

| Command | Engine |
|---|---|
| `bbsctl inspect` | [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector) (required) |
| `bbsctl scan` | `bbsctl-audit` only (legacy) |

**Reference:** [github.com/NVIDIA/SkillSpector](https://github.com/NVIDIA/SkillSpector)  
**Pinned revision (doctor / evidence):** `SKILLSPECTOR_PIN` in `skillctl/lifecycle/config.py` (currently `cf5cac7…`).

### Install SkillSpector

```bash
# Python >= 3.12 required
uv sync --group engines
# or:
uv tool install "git+https://github.com/NVIDIA/SkillSpector@cf5cac7ba5c756a6e0ebf52dc9763f49422f889f"
bbsctl doctor    # skillspector row: available?
```

### Run it

```bash
cd my-skill
bbsctl inspect
# → dist/scan.sarif
# regulated strictness may pass --fail-on-findings through to SkillSpector
```

Legacy (no NVIDIA CLI):

```bash
bbsctl scan      # bbsctl-audit only
```

Pipeline scan stage still follows `[tool.bbsctl.engines] scan` (default `bbsctl-audit`). Prefer `bbsctl inspect` when you want SkillSpector explicitly.

If SkillSpector is missing, exit `2` with a Fix line — install, then re-run `bbsctl inspect`.

---

## Mellea certify

`bbsctl mellea-certify` always runs the **[Mellea skills compiler](https://github.com/generative-computing/mellea-skills-compiler)** (`mellea-skills compile` → `mellea-skills certify`).

| Command | Engine |
|---|---|
| `bbsctl mellea-certify` | [mellea-skills-compiler](https://github.com/generative-computing/mellea-skills-compiler) (required) |
| `bbsctl certify` | Config: `certify = "mellea"` or `"none"` (default) |

**Pinned revision:** `MELLEA_PIN` in `skillctl/lifecycle/config.py`.

```bash
uv sync --group engines
# or:
uv tool install "git+https://github.com/generative-computing/mellea-skills-compiler@<pin>"

bbsctl mellea-certify
# Config-driven (only if certify = "mellea"):
bbsctl certify
bbsctl pipeline --from certify --to certify
```

---

## Author / build / validate

```bash
bbsctl new hello-skill --strictness local
cd hello-skill
bbsctl compile          # frontmatter + agentskills rules → dist/compile-report.json
bbsctl validate --fast  # cheap gates
bbsctl run --prompt "…" # try the skill (default runtime: mock)
```

---

## Eval

```bash
bbsctl eval                     # suites under evals/*.json
bbsctl eval --runtime ollama --judge llm
bbsctl eval --mode smoke        # one case per suite (CI-friendly)
```

Runtimes/judges are pluggable (`mock`, `ollama`, `claude-agent-sdk`, `heuristic`, `llm`). See [`../evaluation.md`](../evaluation.md).

---

## Approve / verify / evidence

```bash
bbsctl pipeline --strictness org   # may exit 3 waiting on approve
bbsctl approve --by alice
bbsctl verify
# Evidence under .bbsctl/evidence/<skill>-<hash>/
```

---

## Publish / discover / marketplace

```bash
bbsctl publish                              # local Claude marketplace
bbsctl publish --marketplace ./team-mp      # team Git marketplace
bbsctl publish artifacts/.../slug --inplace # catalog curation (no copy)

bbsctl discover ./my-skill --domain example.com -o ard.json

bbsctl marketplace init ./team-mp
bbsctl marketplace list ./team-mp
bbsctl marketplace export --catalog ./artifacts --marketplace ./team-mp
```

Details: [how-to-publish.md](how-to-publish.md).

---

## Trust / external skills

```bash
bbsctl fetch <url>          # stage + audit before install
bbsctl audit path/to/skill  # trust audit (spec, scripts, permissions)
bbsctl risk matrix          # control matrix (not a scanner)
```

---

## Pipeline (orchestrator)

```bash
bbsctl pipeline --strictness team
bbsctl pipeline --fast --to compile
bbsctl pipeline --from scan          # resume after an engine fix
```

Full walkthrough: [how-to-run-pipeline.md](how-to-run-pipeline.md).

---

## Config cheat sheet

```toml
[tool.bbsctl]
default_strictness = "team"

[tool.bbsctl.engines]
scan = "skillspector"   # or "bbsctl-audit"
certify = "mellea"      # or "none"
```

Optional engines are **not** in the base wheel — use `uv sync --group engines` so PyPI stays clean (PEP 735).

---

## See also

- [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector) — scan engine
- [mellea-skills-compiler](https://github.com/generative-computing/mellea-skills-compiler) — certify engine
- [`../lifecycle.md`](../lifecycle.md) — stage table
- [`../troubleshooting.md`](../troubleshooting.md) — Fix-line patterns
