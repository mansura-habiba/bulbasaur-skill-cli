# Bulbasaur — build, install from wheel, and try the Phase 2 journey.
#
# Usage:
#   make build        — build the wheel into dist/
#   make install      — build + install wheel into a fresh .try-venv
#   make try          — install + run the end-to-end Phase 2 developer journey
#   make test         — run the test suite via uv
#   make lint         — run ruff via uv
#   make clean        — remove build artifacts and the try workspace

SHELL      := /bin/bash
BBSCTL_DIR := bbsctl
DIST_DIR   := $(BBSCTL_DIR)/dist
TRY_VENV   := .try-venv
TRY_WS     := .try-workspace
PYTHON     := $(TRY_VENV)/bin/python
BBSCTL     := $(TRY_VENV)/bin/bbsctl

# ── Build ────────────────────────────────────────────────────────────────────

.PHONY: build
build:
	@echo "==> Building wheel …"
	cd $(BBSCTL_DIR) && uv build --wheel --out-dir dist
	@echo ""
	@ls -lh $(DIST_DIR)/*.whl
	@echo "==> Wheel ready."

# ── Install from wheel ──────────────────────────────────────────────────────

.PHONY: install
install: build
	@echo ""
	@echo "==> Creating fresh venv at $(TRY_VENV) …"
	uv venv $(TRY_VENV) --python 3.13
	@echo "==> Installing wheel into $(TRY_VENV) …"
	VIRTUAL_ENV=$(CURDIR)/$(TRY_VENV) uv pip install $(DIST_DIR)/bbsctl-*.whl
	@echo ""
	$(BBSCTL) --version
	@echo "==> Installed."

# ── Try: end-to-end Phase 2 journey ─────────────────────────────────────────

.PHONY: try
try: install
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo "  Phase 2 — end-to-end developer journey"
	@echo "════════════════════════════════════════════════════════════════"
	@rm -rf $(TRY_WS)
	@mkdir -p $(TRY_WS)
	@# ── Step 0: project init ────────────────────────────────────────
	@echo ""
	@echo "── 0. bbsctl init (create [tool.bulbasaur] in pyproject.toml) ──"
	cd $(TRY_WS) && uv init --no-readme --name tryproject -q 2>/dev/null || true
	cd $(TRY_WS) && $(CURDIR)/$(BBSCTL) init --strictness team
	@echo ""
	@echo "   pyproject.toml now contains:"
	@grep -A5 '\[tool.bulbasaur\]' $(TRY_WS)/pyproject.toml || true
	@# ── Step 1: scaffold at local ──────────────────────────────────
	@echo ""
	@echo "── 1. bbsctl new my-skill (local strictness) ──"
	cd $(TRY_WS) && $(CURDIR)/$(BBSCTL) new my-skill
	@echo ""
	@echo "   Files created:"
	@ls -R $(TRY_WS)/my-skill
	@# ── Step 2: compile at local ──────────────────────────────────
	@echo ""
	@echo "── 2. bbsctl compile (local) ──"
	cd $(TRY_WS)/my-skill && $(CURDIR)/$(BBSCTL) compile
	@# ── Step 3: climb to team ─────────────────────────────────────
	@echo ""
	@echo "── 3. bbsctl strictness team --yes ──"
	cd $(TRY_WS)/my-skill && $(CURDIR)/$(BBSCTL) strictness team --yes
	@echo ""
	@echo "   skill.yaml:"
	@cat $(TRY_WS)/my-skill/skill.yaml
	@# ── Step 4: validate at team ─────────────────────────────────
	@echo ""
	@echo "── 4. bbsctl validate --fast (team strictness) ──"
	cd $(TRY_WS)/my-skill && $(CURDIR)/$(BBSCTL) validate --fast
	@# ── Step 5: validate JSON output ─────────────────────────────
	@echo ""
	@echo "── 5. bbsctl validate --output json ──"
	cd $(TRY_WS)/my-skill && $(CURDIR)/$(BBSCTL) validate --output json | head -30
	@# ── Step 6: create marketplace ────────────────────────────────
	@echo ""
	@echo "── 6. bbsctl marketplace init ──"
	cd $(TRY_WS) && $(CURDIR)/$(BBSCTL) marketplace init ./my-team-marketplace
	@# ── Step 7: publish to marketplace ────────────────────────────
	@echo ""
	@echo "── 7. bbsctl publish --marketplace ──"
	cd $(TRY_WS)/my-skill && $(CURDIR)/$(BBSCTL) publish --marketplace $(CURDIR)/$(TRY_WS)/my-team-marketplace
	@echo ""
	@echo "   marketplace contents:"
	@ls -R $(TRY_WS)/my-team-marketplace/plugins/
	@# ── Step 8: add skill dependency ──────────────────────────────
	@echo ""
	@echo "── 8. bbsctl add (into a consumer project) ──"
	@mkdir -p $(TRY_WS)/consumer
	cd $(TRY_WS)/consumer && $(CURDIR)/$(BBSCTL) add my-skill-plugin@$(CURDIR)/$(TRY_WS)/my-team-marketplace
	@echo ""
	@echo "   skills.lock:"
	@cat $(TRY_WS)/consumer/skills.lock
	@# ── Step 9: list installed ────────────────────────────────────
	@echo ""
	@echo "── 9. bbsctl list ──"
	cd $(TRY_WS)/consumer && $(CURDIR)/$(BBSCTL) list
	@# ── Step 10: install from lock ────────────────────────────────
	@echo ""
	@echo "── 10. bbsctl install (from skills.lock) ──"
	cd $(TRY_WS)/consumer && $(CURDIR)/$(BBSCTL) install
	@# ── Step 11: remove ──────────────────────────────────────────
	@echo ""
	@echo "── 11. bbsctl remove ──"
	cd $(TRY_WS)/consumer && $(CURDIR)/$(BBSCTL) remove my-skill-plugin
	cd $(TRY_WS)/consumer && $(CURDIR)/$(BBSCTL) list
	@# ── Step 12: scaffold directly at team ────────────────────────
	@echo ""
	@echo "── 12. bbsctl new --strictness team (direct scaffold) ──"
	cd $(TRY_WS) && $(CURDIR)/$(BBSCTL) new team-skill --strictness team
	@echo ""
	@echo "   Files created:"
	@ls $(TRY_WS)/team-skill
	@# ── Step 13: run ──────────────────────────────────────────────
	@echo ""
	@echo "── 13. bbsctl run (mock runtime) ──"
	cd $(TRY_WS)/my-skill && $(CURDIR)/$(BBSCTL) run
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo "  All Phase 2 steps completed successfully."
	@echo "════════════════════════════════════════════════════════════════"

# ── Test / Lint ──────────────────────────────────────────────────────────────

.PHONY: test
test:
	cd $(BBSCTL_DIR) && uv run pytest tests/ -q

.PHONY: lint
lint:
	cd $(BBSCTL_DIR) && uv run ruff check src/skillctl/

# ── Clean ────────────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	rm -rf $(TRY_VENV) $(TRY_WS) $(DIST_DIR)
	@echo "Cleaned."
