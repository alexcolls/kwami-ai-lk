.PHONY: help install dev api agent lint format test clean docker-build docker-up docker-down

# Default target
help:
	@echo "Kwami AI LiveKit - Development Commands"
	@echo ""
	@echo "  make install     - Install dependencies"
	@echo "  make dev         - Install with dev dependencies"
	@echo "  make api         - Run API server (dev mode)"
	@echo "  make agent       - Run agent worker (dev mode)"
	@echo "  make lint        - Run linter"
	@echo "  make format      - Format code"
	@echo "  make test        - Run tests"
	@echo "  make clean       - Clean build artifacts"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  - Build Docker images"
	@echo "  make docker-up     - Start services"
	@echo "  make docker-down   - Stop services"

# =============================================================================
# Development
# =============================================================================

install:
	uv sync

dev:
	uv sync --all-extras

api:
	uv run kwami-api

agent:
	uv run kwami-agent

# =============================================================================
# Code Quality
# =============================================================================

lint:
	uv run ruff check src/

format:
	uv run ruff format src/
	uv run ruff check --fix src/

test:
	uv run pytest

# =============================================================================
# Docker
# =============================================================================

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

# =============================================================================
# Cleanup
# =============================================================================

clean:
	rm -rf .venv/
	rm -rf __pycache__/
	rm -rf src/**/__pycache__/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf dist/
	rm -rf *.egg-info/
