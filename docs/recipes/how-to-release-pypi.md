# Recipe: release bbsctl to PyPI

Publish the `bbsctl` wheel from this repo using GitHub Actions + PyPI Trusted Publishing.

## One-time setup

1. Create a GitHub Environment named **`pypi`** (optional protection rules).
2. On [PyPI → bbsctl → Publishing](https://pypi.org/manage/project/bbsctl/settings/publishing/), add a Trusted Publisher:
   - Owner: `mansura-habiba`
   - Repository: `bulbasaur-skill-cli`
   - Workflow name: `python-publish.yml`
   - Environment name: `pypi`

No PyPI API token is stored in GitHub secrets.

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
pip install -U bbsctl
bbsctl --version
```

Workflow source: [`.github/workflows/python-publish.yml`](../../.github/workflows/python-publish.yml).
