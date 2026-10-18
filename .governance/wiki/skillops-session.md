# Wiki: bbsctl lifecycle session

**Date:** 2026-10-18  
**Branch:** `feat/skillops-orchestrator`  
**Task:** BBS-200  

## Decisions

- **One CLI:** `bbsctl` only. No second `skillops` binary. Package is `skillctl.lifecycle`; config `[tool.bbsctl]`; GH Action `bbsctl-pipeline`.
- **Distribution verbs:** `bbsctl publish` (install packaging) + `bbsctl discover` (ARD emit). That is the full user-facing surface for “get it out” / “make it findable.”
- **`bbsctl marketplace` is admin only:** `init` / `list` / `export`. Not a third user verb for publish/ard.
- Catalog in-place Claude marketplace (`--inplace`) is a *target* of `publish`, not a separate command tree.
- ARD is emit-only under `discover` (optional `--ard` on publish). No ARD search registry in bbsctl.
- Issue/project board update deferred until `gh auth refresh` succeeds (IBM + public tokens invalid).

## Layout

- Stages: `bbsctl/src/skillctl/lifecycle/`
- Commands: `inspect` (SkillSpector), `scan` (legacy bbsctl-audit), `mellea-certify` (Mellea), `certify` (config), `approve`, `verify`, `doctor`, `pipeline`, `publish`, `discover`
- Engine-forcing pattern: dedicated verb + `engine_override=` on `run_single_stage` (`inspect` → SkillSpector, `mellea-certify` → Mellea). Config-driven aliases remain for pipeline/`certify`.
- Stage CLIs share `add_stage_command_args` in `stage_cmd.py`. Mellea adapter helpers (`find_compiled_dir`, `collect_audit`, `_run`) are unit-tested in `test_mellea_engine.py`.

- Docs: `docs/lifecycle.md`, `docs/recipes/how-to-commands.md`, README “How to use it”
- Issue: [#4](https://github.com/mansura-habiba/bulbasaur-skill-cli/issues/4) — project board add blocked (`gh auth refresh -s read:project` / `project`).
