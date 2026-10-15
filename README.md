# FX Rates ETL Pipeline

A small, production-shaped data pipeline that ingests foreign exchange rates from a public API (or a CSV file), validates and transforms them with pandas, runs data quality checks, and loads the result into PostgreSQL. It is idempotent, tested, containerised, and runs with zero setup against a local SQLite file.

Built to show how I approach real pipeline work: the specification is the source of truth, every stage is testable, bad data never reaches the database, and re-running is always safe.

## What it demonstrates

| Area | Where to look |
|------|---------------|
| REST API ingestion with retries and backoff | `extract.py` (httpx + tenacity) |
| Multiple sources (API and CSV file) behind one interface | `extract.py` |
| Cleaning, typing, deduplication and derived metrics | `transform.py` (pandas) |
| Data quality checks with critical and warning severities | `quality.py` |
| Idempotent upsert, dialect aware for Postgres and SQLite | `load.py` (SQLAlchemy 2.x) |
| Row level validation before load | `models.py` (pydantic) |
| Configuration from environment, sensible defaults | `config.py` (pydantic-settings) |
| Structured logging | `logging_config.py` |
| Orchestration ready | `flow.py` (optional Prefect flow) |
| Tests for every stage | `tests/` (pytest) |
| Containerisation and CI | `Dockerfile`, `docker-compose.yml`, GitHub Actions |

## How it works

```
  API (Frankfurter)  ─┐
                      ├─► extract ─► transform ─► quality ─► load ─► PostgreSQL
  CSV file           ─┘   (fetch,     (clean,     (checks)   (upsert)   / SQLite
                           retry)      derive)
```

The pipeline fetches a date range of rates for a base currency against a set of quote currencies, flattens the nested payload into tidy rows, computes the day-on-day percentage change per currency pair, checks the result, and upserts it. Running the same date range twice updates the existing rows rather than duplicating them.

## Quick start

No API key is required. The default configuration writes to a local SQLite file, so the pipeline runs immediately.

```bash
pip install -r requirements-dev.txt

# Run against the bundled sample CSV (no network needed)
make run-file

# Or run against the live API for the last 7 days
make run

# Or a specific date range
PYTHONPATH=src python -m fx_etl.cli --start 2024-01-01 --end 2024-01-31
```

Run the tests:

```bash
make test
```

## Running against PostgreSQL

A Compose file brings up PostgreSQL and runs the pipeline against it:

```bash
docker compose up -d db
docker compose run --rm etl --start 2024-01-01 --end 2024-01-31
```

Or point the pipeline at any database by setting one variable:

```bash
export FX_DATABASE_URL=postgresql+psycopg2://fx:fx@localhost:5432/fx
make run
```

## Configuration

All settings are read from the environment (or a `.env` file). Copy `.env.example` to `.env` to change them.

| Variable | Default | Purpose |
|----------|---------|---------|
| `FX_DATABASE_URL` | `sqlite:///fx.db` | Any SQLAlchemy URL |
| `FX_API_BASE_URL` | `https://api.frankfurter.dev/v1` | Source API |
| `FX_BASE_CURRENCY` | `USD` | Base currency |
| `FX_SYMBOLS` | `EUR,GBP,JPY,CNY,ETB` | Quote currencies |
| `FX_MAX_RETRIES` | `4` | API retry attempts |
| `FX_LOG_LEVEL` | `INFO` | Logging level |

## Data quality

Checks run between transform and load. Critical failures stop the pipeline so bad data never lands; warnings are logged and allowed through.

- **Critical:** data is present, no nulls in key columns, all rates positive, no duplicate (date, base, quote) rows.
- **Warning:** all requested currencies present, no implausible daily moves above 25 percent.

## Project structure

```
src/fx_etl/
  config.py           settings from environment
  logging_config.py   structured logging
  models.py           SQLAlchemy schema + pydantic validation
  extract.py          API and CSV ingestion with retries
  transform.py        pandas cleaning and derived metrics
  quality.py          data quality checks
  load.py             idempotent dialect-aware upsert
  pipeline.py         orchestrates the stages
  cli.py              command-line entry point
  flow.py             optional Prefect orchestration
tests/                pytest coverage for every stage
```

## Design notes

- **Idempotent by design.** The load uses an `ON CONFLICT` upsert keyed on (date, base, quote), so a re-run corrects values instead of duplicating rows. Pipelines get re-run, and that should never be a problem.
- **The specification decides, not the demo.** Quality checks encode what the data must satisfy, and the pipeline refuses to load anything that fails a critical check.
- **Practical, not over-engineered.** SQLite for zero-setup local runs, PostgreSQL for the real thing, the same code path for both. Prefect is available for scheduling but the core pipeline has no heavy dependencies.

## Licence

MIT. Built by Abel Tadesse. Code: [github.com/ab3lT](https://github.com/ab3lT)
