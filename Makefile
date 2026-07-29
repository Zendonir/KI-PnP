.DEFAULT_GOAL := help
.PHONY: help up down logs build restart migrate revision test test-backend typecheck lint fmt clean

help: ## Zeigt diese Uebersicht
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Startet die gesamte Plattform
	docker compose up -d --build

down: ## Stoppt alles (Daten bleiben erhalten)
	docker compose down

logs: ## Folgt den Backend-Logs
	docker compose logs -f backend

restart: ## Baut das Backend neu und startet es
	docker compose up -d --build backend

migrate: ## Spielt ausstehende Migrationen ein
	docker compose exec backend alembic upgrade head

revision: ## Erzeugt eine Migration (make revision m="beschreibung")
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

test: test-backend typecheck ## Fuehrt alle Pruefungen aus

test-backend: ## Backend-Tests (SQLite, ohne Docker)
	cd backend && .venv/bin/python -m pytest -q

typecheck: ## Strikte Typpruefung des Frontends
	cd frontend && npm run typecheck

lint: ## Statische Analyse des Backends
	cd backend && .venv/bin/python -m ruff check app tests

fmt: ## Formatiert das Backend
	cd backend && .venv/bin/python -m ruff format app tests

clean: ## Entfernt lokale Artefakte
	rm -rf backend/*.db frontend/dist frontend/dev-dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
