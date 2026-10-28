# Command shortcuts. Recipes run in PowerShell 7 (pwsh) on Windows.
SHELL := pwsh.exe
.SHELLFLAGS := -NoProfile -NoLogo -Command

APP := app/main.py
OLLAMA_MODEL ?= qwen2.5:0.5b

.DEFAULT_GOAL := help
.PHONY: help install env model dev run test lint format check clean

help: ## Show available commands
	@Select-String -Path $(firstword $(MAKEFILE_LIST)) -Pattern '^([a-zA-Z_-]+):.*?## (.*)$$' | ForEach-Object { '{0,-10} {1}' -f $$_.Matches[0].Groups[1].Value, $$_.Matches[0].Groups[2].Value }

install: ## Install Python 3.11 and all dependencies (incl. dev)
	uv python install 3.11
	uv sync

env: ## Create .env from .env.example (if missing)
	@if (-not (Test-Path .env)) { Copy-Item .env.example .env; 'Created .env' } else { '.env already exists' }

model: ## Pull the Ollama model (override with OLLAMA_MODEL=...)
	ollama pull $(OLLAMA_MODEL)

dev: ## Run the API with auto-reload (http://127.0.0.1:8000/docs)
	uv run fastapi dev $(APP)

run: ## Run the API without reload
	uv run fastapi run $(APP)

test: ## Run the test suite
	uv run pytest

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-fix lint issues and format code
	uv run ruff check --fix .
	uv run ruff format .

check: lint test ## Lint + tests (run before committing)

clean: ## Remove caches
	@Get-ChildItem -Recurse -Directory -Include __pycache__, .pytest_cache, .ruff_cache | Remove-Item -Recurse -Force
