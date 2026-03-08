.PHONY: install lint test run migrate bootstrap

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -e .[dev]

lint:
	ruff check .

test:
	pytest

run:
	uvicorn arkashri.main:app --reload

migrate:
	alembic upgrade head

bootstrap:
	docker compose up -d db && . .venv/bin/activate && alembic upgrade head && curl -s -X POST http://127.0.0.1:8000/bootstrap/minimal >/dev/null
