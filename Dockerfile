# syntax=docker/dockerfile:1
# Kwami AI LiveKit - Multi-stage Dockerfile
# Supports both API server and Agent worker

FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ ./src/

# =============================================================================
# API Server Target
# =============================================================================
FROM base AS api

EXPOSE 8080

ENV APP_ENV=production
ENV API_HOST=0.0.0.0
ENV API_PORT=8080

CMD ["uv", "run", "kwami-api"]

# =============================================================================
# Agent Worker Target
# =============================================================================
FROM base AS agent

# Agent workers don't need to expose ports - they connect outbound to LiveKit

ENV APP_ENV=production

CMD ["uv", "run", "kwami-agent"]
