.PHONY: install dev test run run-file docker-up docker-run clean

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

docker-up:
	docker compose up -d db

docker-run:
	docker compose run --rm etl --start 2024-01-01 --end 2024-01-31

clean:
	rm -f fx.db
	find . -type d -name __pycache__ -exec rm -rf {} +
