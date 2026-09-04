.PHONY: up down logs test test-integration lint format migrate revision openapi

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	pytest -q

test-integration:
	RUN_INTEGRATION_TESTS=1 pytest -q -m integration

lint:
	ruff check .

format:
	ruff format .

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

openapi:
	python scripts/export_openapi.py
