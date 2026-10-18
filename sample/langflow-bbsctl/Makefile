# Langflow + bbsctl sample helpers (Docker or Podman).
SHELL := /bin/bash
SAMPLE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(SAMPLE_DIR)/../..)
WHEEL_SRC := $(REPO_ROOT)/bbsctl/dist
WHEEL_DST := $(SAMPLE_DIR)/wheels
IMAGE ?= localhost/langflow-bbsctl-sample:local
PORT ?= 7860
UV ?= uv
PYTHON ?= python3
CONTAINER ?= $(shell command -v podman >/dev/null && echo podman || echo docker)

.PHONY: wheel test docker-build docker-up docker-down podman-build podman-up podman-down clean-wheels

wheel:
	@mkdir -p $(WHEEL_DST)
	@test -n "$$(ls $(WHEEL_SRC)/bbsctl-*.whl 2>/dev/null)" || (cd $(REPO_ROOT) && $(MAKE) build)
	cp -f $(WHEEL_SRC)/bbsctl-*.whl $(WHEEL_DST)/
	@ls -lh $(WHEEL_DST)/bbsctl-*.whl

test:
	cd $(SAMPLE_DIR) && (command -v $(UV) >/dev/null && $(UV) run --with pytest pytest tests/ -q || $(PYTHON) -m pytest tests/ -q)

docker-build podman-build: wheel
	$(CONTAINER) build -t $(IMAGE) -f $(SAMPLE_DIR)/Dockerfile $(SAMPLE_DIR)

docker-up: wheel
	docker compose -f $(SAMPLE_DIR)/docker-compose.yml up --build -d
	@echo "Langflow UI: http://localhost:$(PORT)"

podman-up: podman-build
	-$(CONTAINER) rm -f langflow-bbsctl
	$(CONTAINER) run -d --name langflow-bbsctl -p $(PORT):7860 \
		-e LANGFLOW_AUTO_LOGIN=true $(IMAGE)
	@echo "Langflow UI: http://localhost:$(PORT)"

docker-down:
	docker compose -f $(SAMPLE_DIR)/docker-compose.yml down

podman-down:
	-$(CONTAINER) rm -f langflow-bbsctl

clean-wheels:
	rm -f $(WHEEL_DST)/*.whl
