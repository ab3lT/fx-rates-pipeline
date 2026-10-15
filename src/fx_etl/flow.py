"""Optional Prefect orchestration.

This wraps the same pipeline stages as Prefect tasks so the pipeline can be
scheduled, retried and observed in a Prefect deployment. Prefect is an optional
dependency; install it with `pip install prefect` before using this module.

    prefect server start          # in one terminal
    python -m fx_etl.flow         # run the flow once
"""

from __future__ import annotations

import datetime as dt

from prefect import flow, task  # type: ignore[import-not-found]

from . import extract, load, quality, transform
from .config import get_settings


@task(retries=3, retry_delay_seconds=5)
def extract_task(settings, start, end):
    import httpx

    with httpx.Client(timeout=settings.request_timeout) as client:
        payload = extract.fetch_timeseries(
            client, settings.api_base_url, start, end,
            settings.base_currency, settings.symbols, settings.max_retries,
        )
    return extract.normalise_timeseries(payload)


@task
def transform_task(records):
    return transform.transform(records)


@task
def quality_task(frame, symbols):
    report = quality.run_checks(frame, expected_symbols=symbols)
    if not report.ok:
        raise quality.DataQualityError("critical data quality checks failed")
    return frame


@task
def load_task(settings, frame):
    engine = load.get_engine(settings.database_url)
    load.init_db(engine)
    return load.upsert_frame(engine, frame)


@flow(name="fx-rates-etl")
def fx_rates_flow(start: dt.date | None = None, end: dt.date | None = None) -> int:
    settings = get_settings()
    end = end or dt.date.today()
    start = start or (end - dt.timedelta(days=7))

    records = extract_task(settings, start, end)
    frame = transform_task(records)
    frame = quality_task(frame, settings.symbols)
    return load_task(settings, frame)


if __name__ == "__main__":
    fx_rates_flow()
