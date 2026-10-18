# CUGA skill-contract eval staging (local wheel until PyPI).
SHELL := /bin/bash
SAMPLE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(SAMPLE_DIR)/../..)
WHEEL := $(REPO_ROOT)/bbsctl/dist/bbsctl-*.whl
FIXTURE := $(SAMPLE_DIR)/fixtures/demo-skill
VENV := $(SAMPLE_DIR)/.venv

.PHONY: wheel-check skill-eval clean

wheel-check:
	@test -n "$$(ls $(WHEEL) 2>/dev/null)" || (cd $(REPO_ROOT) && make build)
	@ls -lh $(WHEEL)

skill-eval: wheel-check
	@rm -rf $(VENV)
	uv venv $(VENV) --python 3.12
	VIRTUAL_ENV=$(VENV) uv pip install $(WHEEL)
	$(VENV)/bin/bbsctl --version
	$(VENV)/bin/bbsctl compile $(FIXTURE) --output text
	$(VENV)/bin/bbsctl validate $(FIXTURE) --fast --output text
	@echo "==> skill-eval OK for $(FIXTURE)"
	@echo "    Optional: $(VENV)/bin/bbsctl eval $(FIXTURE) --mode smoke --runtime mock"

clean:
	rm -rf $(VENV) $(FIXTURE)/dist
