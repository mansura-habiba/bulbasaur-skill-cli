# Progress

## BBS-200 — bbsctl lifecycle pipeline

| When | Milestone | Notes |
|---|---|---|
| 2026-10-18 | Started | Branch `feat/skillops-orchestrator`; plan superseded by `docs/lifecycle.md`. |
| 2026-10-18 | Docs | Deleted obsolete `docs/skillops-plan.md` (second-CLI plan); canonical doc is `docs/lifecycle.md`. |
| 2026-10-18 | Idempotency | Added `skillctl.durable`; hardened catalog/ARD/team publish + evidence/approve; audit in wiki; principle #7. |
| 2026-10-18 | Docs prune | Deleted placeholders / outdated aspirational docs (best-practices, spec-guidelines, ide-integration, whitepaper, Phase 2/3 recipe stubs); fixed README/quickstart links; tightened `.gitignore`. |
| 2026-10-18 | Pins | SkillSpector `cf5cac7…`; Mellea `1538a08…`. |
| 2026-10-18 | Naming | Product is **`bbsctl` only**. Dropped "skillops" brand. Package `skillctl.lifecycle`, config `[tool.bbsctl]`, action `bbsctl-pipeline`. |
| 2026-10-18 | Verify | `tests/test_lifecycle_pipeline.py` green. |
| 2026-10-18 | Dist verbs | User-facing surface is **`bbsctl publish`** + **`bbsctl discover`** only. `marketplace` kept as admin (`init`/`list`/`export`). ARD under discover; catalog `--inplace` under publish. |
| 2026-10-18 | Naming | Removed IBM-specific **OIC** branding. Module `catalog_publish`, flag `--inplace`, generic catalog/curation wording. |
| 2026-10-18 | Idempotency gaps | `file_lock` on marketplace upserts; export checkpoint + `--fresh`; pipeline exit-2 resume Fix via `--from`. |
| 2026-10-18 | Recipe | Added `docs/recipes/how-to-commands.md` — command ↔ engine map. |
| 2026-10-18 | Inspect | Added `bbsctl inspect` → NVIDIA SkillSpector. `bbsctl scan` is legacy (`bbsctl-audit` only). |
| 2026-10-18 | Recipes | Added `docs/recipes/how-to-publish.md` and `docs/recipes/how-to-run-pipeline.md`; linked from quickstart. |
| 2026-10-18 | Roadmap | Rewrote `docs/bbsctl-roadmap.md`: §0 shipped inventory (lifecycle, publish/discover, P0 eval runtime); open P0 = RegressionEvaluator/FULL only; sprint plan renumbered S1′+. |
| 2026-10-18 | Mellea certify | Added `bbsctl mellea-certify` → force Mellea (parallel to `inspect`). `bbsctl certify` stays config-driven. Issue [#4](https://github.com/mansura-habiba/bulbasaur-skill-cli/issues/4). |
| 2026-10-18 | Coverage/quality | DRY `add_stage_command_args`; hardened `MelleaEngine` (helpers, `shutil.copy2`); `test_mellea_engine.py` covers pin, compile/certify paths, CLI force-vs-config. |
| 2026-10-18 | PyPI release | Fixed hatch readme (`bbsctl/README.md`); hardened `.github/workflows/python-publish.yml` (release / `v*` / dispatch, smoke-import, Trusted Publishing + attestations). BBS-202. |
