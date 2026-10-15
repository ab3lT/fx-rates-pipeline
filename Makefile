.PHONY: install dev test run run-file web scheduler docker-up docker-run prod-up prod-logs clean

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

test:
	python -m pytest -q

# Run against the live API for the last 7 days (SQLite by default).
run:
	PYTHONPATH=src python -m fx_etl.cli

# Run against the bundled sample CSV (no network needed).
run-file:
	PYTHONPATH=src python -m fx_etl.cli --source file --file data/seed_rates.csv

# Dashboard on http://127.0.0.1:5000 (SQLite by default).
web:
	PYTHONPATH=src flask --app fx_etl.web run --debug

# Backfill on first start, then run the pipeline every FX_SCHEDULE_HOURS.
scheduler:
	PYTHONPATH=src python -m fx_etl.web.scheduler

docker-up:
	docker compose up -d db

docker-run:
	docker compose run --rm etl --start 2024-01-01 --end 2024-01-31

prod-up:
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

prod-logs:
	docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f --tail=100

clean:
	rm -f fx.db
	find . -type d -name __pycache__ -exec rm -rf {} +
