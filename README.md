# Bulbasaur

A skill framework for agentic development. Skills are versioned, signed, owned, monitored, and evaluated like production code — but only when the developer is ready for them to be.

> **The five-minute promise.** A fresh developer with `uv` installed can scaffold and run their first skill in under five minutes. No marketplace setup. No signing. No ownership document. No policy configuration. Friction climbs with the strictness level the developer opts into, never ahead of it.

## Quickstart

`uv` is the canonical Python toolchain — [install it first](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it.

```bash
# Trial without installing
uvx bbsctl new hello-skill
cd hello-skill && uvx bbsctl compile && uvx bbsctl run

# Or install into a project
uv add bbsctl
bbsctl new hello-skill
cd hello-skill && bbsctl compile && bbsctl run
```

See [`quickstart/`](quickstart/) for the five-minute walkthrough and [`docs/quickstart.md`](docs/quickstart.md) for the longer guide.

## The strictness ladder

| Level | What the framework requires | Typical use |
|---|---|---|
| `local` (default) | Public-spec valid `SKILL.md` only | Solo dev, prototyping |
| `team` | + author identity, ownership stub, light marketplace | Small-team workflows |
| `org` | + full validators, signing, OTel, cost budgets, ownership | Production internal use |
| `regulated` | + regulatory sign-off, retention SLAs, strict gates | High-risk workflows |

Climb the ladder one step at a time:

```bash
bbsctl strictness team    # adds skill.yaml with team-tier minimum, prompts for ownership stub
bbsctl strictness org     # adds the full enterprise overlay, prompts to sign
```

The framework does not force escalation. The marketplace is the gate that refuses to host skills below its declared strictness.

## Documentation

- [`docs/quickstart.md`](docs/quickstart.md) — five-minute walkthrough
- [`docs/strictness-levels.md`](docs/strictness-levels.md) — the strictness axis explained
- [`docs/spec-guidelines.md`](docs/spec-guidelines.md) — the spec, aligned with [agentskills.io](https://agentskills.io)
- [`docs/design-patterns.md`](docs/design-patterns.md) — skill design patterns
- [`docs/best-practices.md`](docs/best-practices.md) — authoring guidance
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — error → fix table

## Architecture

- [`mental-model.md`](mental-model.md) — the framework's mental model
- [`framework-build-plan.md`](framework-build-plan.md) — the engineering plan
- [`mellea-analysis.md`](mellea-analysis.md) — analysis of Mellea Skills Compiler
- [`mcp-composer-analysis.md`](mcp-composer-analysis.md) — analysis of MCP Composer

## Project layout

```
bulbasaur/
├── quickstart/              the five-minute experience
├── docs/                    designer artifacts + recipes
├── templates/               scaffolds, organized by strictness
├── spec/                    schemas (public + enterprise)
├── skillctl/                the CLI (Python ≥3.11)
├── platform/                services (Phase 3+)
├── policies/                default Rego policies
├── reference-plugins/       full-featured demos
└── examples/                CI/CD and toolchain integration examples
```

## License

Apache 2.0.
