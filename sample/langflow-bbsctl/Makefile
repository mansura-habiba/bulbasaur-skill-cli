# Langflow + bbsctl sample helpers.
SHELL := /bin/bash
SAMPLE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(SAMPLE_DIR)/../..)
WHEEL_SRC := $(REPO_ROOT)/bbsctl/dist
WHEEL_DST := $(SAMPLE_DIR)/wheels
IMAGE ?= langflow-bbsctl-sample
PORT ?= 7860
UV ?= uv
PYTHON ?= python3

.PHONY: wheel test docker-build docker-up docker-down clean-wheels

wheel:
	@mkdir -p $(WHEEL_DST)
	@test -n "$$(ls $(WHEEL_SRC)/bbsctl-*.whl 2>/dev/null)" || (echo "missing wheel under $(WHEEL_SRC)"; exit 1)
	cp -f $(WHEEL_SRC)/bbsctl-*.whl $(WHEEL_DST)/
	@ls -lh $(WHEEL_DST)/bbsctl-*.whl

test:
	cd $(SAMPLE_DIR) && (command -v $(UV) >/dev/null && $(UV) run --with pytest pytest tests/ -q || $(PYTHON) -m pytest tests/ -q)

docker-build: wheel
	docker build -t $(IMAGE) -f $(SAMPLE_DIR)/Dockerfile $(SAMPLE_DIR)

docker-up: wheel
	docker compose -f $(SAMPLE_DIR)/docker-compose.yml up --build -d
	@echo "Langflow UI: http://localhost:$(PORT)"

docker-down:
	docker compose -f $(SAMPLE_DIR)/docker-compose.yml down

clean-wheels:
	rm -f $(WHEEL_DST)/*.whl
