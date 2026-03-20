# ──────────────────────────────────────────────────────────────────────────────
# Crypto Trading Agent — Makefile
# Run: make <command>
# ──────────────────────────────────────────────────────────────────────────────

.DEFAULT_GOAL := help
.PHONY: help install dev test test-unit test-integration test-cov lint format typecheck clean db-init db-migrate run docker-up docker-down

# ── Detect Python ──────────────────────────────────────────────────────────────
PYTHON := python3
PIP    := pip3

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Crypto Trading Agent — Available Commands"
	@echo ""
	@echo "  Setup:"
	@echo "    make install       Install all dependencies"
	@echo "    make dev           Install dev + all optional dependencies"
	@echo ""
	@echo "  Database:"
	@echo "    make db-init       Apply all Alembic migrations"
	@echo "    make db-migrate    Generate new migration (set MSG=description)"
	@echo ""
	@echo "  Running:"
	@echo "    make run           Start the trading backend"
	@echo "    make run-reload    Start with hot-reload (dev mode)"
	@echo ""
	@echo "  Testing:"
	@echo "    make test          Run all tests"
	@echo "    make test-unit     Run unit tests only"
	@echo "    make test-cov      Run tests with coverage report"
	@echo ""
	@echo "  Code Quality:"
	@echo "    make lint          Run Ruff linter"
	@echo "    make format        Format code with Ruff"
	@echo "    make typecheck     Run mypy type checker"
	@echo ""
	@echo "  Docker:"
	@echo "    make docker-up     Start all services with docker-compose"
	@echo "    make docker-down   Stop all services"
	@echo "    make docker-logs   View backend logs"
	@echo ""
	@echo "  Other:"
	@echo "    make clean         Remove cache, build artifacts, test data"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	$(PIP) install -r requirements.txt

dev:
	$(PIP) install -e ".[all]"

# ── Database ──────────────────────────────────────────────────────────────────
db-init:
	alembic upgrade head

MSG ?= auto_migration
db-migrate:
	alembic revision --autogenerate -m "$(MSG)"

# ── Run ───────────────────────────────────────────────────────────────────────
run:
	uvicorn src.core.server:app --host 0.0.0.0 --port 8000

run-reload:
	uvicorn src.core.server:app --host 0.0.0.0 --port 8000 --reload --log-level info

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-cov:
	pytest tests/unit/ --cov=app --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ── Code Quality ──────────────────────────────────────────────────────────────
lint:
	ruff check app/ tests/

format:
	ruff format app/ tests/

typecheck:
	mypy app/ --ignore-missing-imports

# ── Docker ────────────────────────────────────────────────────────────────────
docker-up:
	cd docker && docker-compose up --build -d
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend: http://localhost:3000"
	@echo "API Docs: http://localhost:8000/docs"

docker-down:
	cd docker && docker-compose down

docker-logs:
	cd docker && docker-compose logs -f backend

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .coverage htmlcov/ .mypy_cache dist/ build/ *.egg-info
	@echo "Cleaned ✓"
