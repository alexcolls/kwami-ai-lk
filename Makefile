.PHONY: help api agent api-install agent-install lint format clean docker-build docker-up docker-down

help:
	@echo "Kwami AI LiveKit - Development Commands"
	@echo ""
	@echo "API (Token Endpoint):"
	@echo "  make api           - Run API server (dev mode)"
	@echo "  make api-install   - Install API dependencies"
	@echo ""
	@echo "Agent (LiveKit Cloud):"
	@echo "  make agent         - Run agent locally (dev mode)"
	@echo "  make agent-install - Install agent dependencies"
	@echo "  make agent-deploy  - Deploy agent to LiveKit Cloud"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          - Run linter on both projects"
	@echo "  make format        - Format code in both projects"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  - Build API Docker image"
	@echo "  make docker-up     - Start API container"
	@echo "  make docker-down   - Stop API container"

# =============================================================================
# API
# =============================================================================

api-install:
	cd api && uv sync

api:
	cd api && uv run python main.py

# =============================================================================
# Agent
# =============================================================================

agent-install:
	cd agent && uv sync

agent:
	cd agent && uv run python agent.py dev

agent-deploy:
	cd agent && lk agent deploy

# =============================================================================
# Code Quality
# =============================================================================

lint:
	cd api && uv run ruff check .
	cd agent && uv run ruff check .

format:
	cd api && uv run ruff format . && uv run ruff check --fix .
	cd agent && uv run ruff format . && uv run ruff check --fix .

# =============================================================================
# Docker (API only - agent deploys to LiveKit Cloud)
# =============================================================================

docker-build:
	docker build -t kwami-lk-api ./api

docker-up:
	docker run -d --name kwami-lk-api -p 8080:8080 --env-file .env kwami-lk-api

docker-down:
	docker stop kwami-lk-api && docker rm kwami-lk-api

# =============================================================================
# Cleanup
# =============================================================================

clean:
	rm -rf api/.venv api/__pycache__ api/**/__pycache__
	rm -rf agent/.venv agent/__pycache__ agent/**/__pycache__
	rm -rf .pytest_cache .ruff_cache
