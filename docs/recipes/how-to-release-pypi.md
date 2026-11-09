# Recipe: release skill-pipeline to PyPI

Publish the `skill-pipeline` wheel (CLI entry point `bbsctl`) from this repo using GitHub Actions + PyPI Trusted Publishing.

## One-time setup

1. Create a GitHub Environment named **`pypi`** (optional protection rules).
2. **Before the first upload** the project does not exist yet. Add a *pending* Trusted Publisher under your account (not a project page):
   [PyPI → Your account → Publishing](https://pypi.org/manage/account/publishing/)
   - PyPI project name: `skill-pipeline` (must match `[project].name` in `bbsctl/pyproject.toml`)
   - Owner: `mansura-habiba`
   - Repository: `bulbasaur-skill-cli`
   - Workflow name: `python-publish.yml` (filename only)
   - Environment name: `pypi` (required: the workflow sets `environment: pypi`)
3. After the first successful upload, the pending publisher converts into a normal one and creates [pypi.org/p/skill-pipeline](https://pypi.org/p/skill-pipeline). Later releases use the project Publishing settings.

No PyPI API token is stored in GitHub secrets.

### If the publisher stays pending

The pending form only clears after a successful Trusted Publishing upload whose OIDC claims match every field above. Typical blockers:

- Package name in the pending form ≠ `skill-pipeline` in the built METADATA (earlier miss: pending was `skill-manage` while METADATA was still `bbsctl`)
- Environment blank on PyPI while the workflow uses `pypi` (or the reverse)
- Workflow filename typo (must be exactly `python-publish.yml`)
- Last publish job failed before upload finished (check the Actions run log)

Fix a wrong pending name by deleting it and adding a new pending publisher with project name `skill-pipeline` and the GitHub fields above. Do not leave a second pending publisher pointing at a different project name.

## Publish a release

1. Bump `version` in `bbsctl/pyproject.toml` if needed.
2. Prefer a **GitHub Release** (or manual dispatch). Bare `v*` tag pushes only build+test — they do not upload — so creating a Release from a tag cannot double-publish.

```bash
git tag v0.1.1
git push origin v0.1.1          # build+test only
gh release create v0.1.1 --generate-notes   # publishes via Trusted Publishing
```

Or run the workflow manually:

```bash
gh workflow run python-publish.yml -f publish_to_pypi=true
```

Dry-run (build + test only, no upload):

```bash
gh workflow run python-publish.yml -f publish_to_pypi=false
```

The publish job uses `skip-existing: true` and a `concurrency:` group keyed on the ref.

## Verify

```bash
pip install -U skill-pipeline
bbsctl --version
```

Workflow source: [`.github/workflows/python-publish.yml`](../../.github/workflows/python-publish.yml).
