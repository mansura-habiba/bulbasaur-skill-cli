#!/usr/bin/env bash
# Bulbasaur quickstart smoke test.
#
# Runs the documented five-minute flow end-to-end on a fresh machine.
# Fails the build if total wall-clock exceeds 300 seconds.
#
# Invoked by .github/workflows/quickstart-smoke.yml on every PR.

set -euo pipefail

QUICKSTART_BUDGET_SECONDS=${QUICKSTART_BUDGET_SECONDS:-300}
WORKDIR=$(mktemp -d -t bulbasaur-quickstart-XXXXXX)
trap 'rm -rf "$WORKDIR"' EXIT

cd "$WORKDIR"

START_TIME=$(date +%s)

step() {
  local label=$1
  shift
  echo
  echo "::group::$label"
  echo "+ $*"
  "$@"
  echo "::endgroup::"
}

# Step 1 — install skillctl into an isolated env.
# Prefer uv when available, fall back to pip.
if command -v uv >/dev/null 2>&1; then
  step "install (uv)" uv venv .venv --python 3.11
  # shellcheck disable=SC1091
  source .venv/bin/activate
  step "install (uv add)" uv pip install -e "${SKILLCTL_SRC:-$GITHUB_WORKSPACE/skillctl}"
else
  step "install (pip)" python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  step "install (pip)" python3 -m pip install --quiet --upgrade pip
  step "install (pip install)" python3 -m pip install --quiet -e "${SKILLCTL_SRC:-$GITHUB_WORKSPACE/skillctl}"
fi

# Step 2 — scaffold.
step "scaffold" skillctl new hello-skill

# Step 3 — compile.
cd hello-skill
step "compile" skillctl compile

# Step 4 — run.
step "run" skillctl run

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo
echo "================================================================"
echo "Quickstart elapsed: ${ELAPSED}s (budget: ${QUICKSTART_BUDGET_SECONDS}s)"
echo "================================================================"

if [ "$ELAPSED" -gt "$QUICKSTART_BUDGET_SECONDS" ]; then
  echo "ERROR: quickstart exceeded the five-minute budget."
  echo "  Detail: elapsed ${ELAPSED}s > budget ${QUICKSTART_BUDGET_SECONDS}s"
  echo "  Fix:    profile each step above to find the regression."
  echo "          See docs/quickstart.md for the per-step budgets."
  exit 1
fi

echo "OK"
