"""Pipeline orchestrator: wire extract, transform, quality and load together."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

import httpx

from . import extract, load, quality, transform
from .config import Settings, get_settings
from .logging_config import configure_logging, get_logger

logger = get_logger(__name__)


@dataclass
class PipelineResult:
    rows_loaded: int
    quality_ok: bool
    duration_seconds: float
    report: quality.QualityReport


def _extract_records(settings: Settings, start: dt.date, end: dt.date, source: str, file: str | None) -> list[dict[str, Any]]:
    if source == "file":
        if not file:
            raise ValueError("source=file requires a file path")
        return extract.load_records_from_csv(file)

    with httpx.Client(timeout=settings.request_timeout) as client:
        payload = extract.fetch_timeseries(
            client=client,
            base_url=settings.api_base_url,
            start=start,
            end=end,
            base_currency=settings.base_currency,
            symbols=settings.symbols,
            max_retries=settings.max_retries,
        )
    return extract.normalise_timeseries(payload)


def run_pipeline(
    settings: Settings | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    source: str = "api",
    file: str | None = None,
) -> PipelineResult:
    """Run the full ETL and return a summary.

    Dates default to the last 7 days when not supplied.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    end = end or dt.date.today()
    start = start or (end - dt.timedelta(days=7))

    started = time.perf_counter()
    logger.info(
        "pipeline start source=%s start=%s end=%s base=%s symbols=%s",
        source, start, end, settings.base_currency, settings.symbols,
    )

    records = _extract_records(settings, start, end, source, file)
    frame = transform.transform(records)
    report = quality.run_checks(frame, expected_symbols=settings.symbols)

    if not report.ok:
        failed = [r.name for r in report.results if r.critical and not r.passed]
        raise quality.DataQualityError(f"critical checks failed: {failed}")

    engine = load.get_engine(settings.database_url)
    load.init_db(engine)
    rows_loaded = load.upsert_frame(engine, frame)

    duration = time.perf_counter() - started
    logger.info("pipeline done rows=%d duration=%.2fs", rows_loaded, duration)

    return PipelineResult(
        rows_loaded=rows_loaded,
        quality_ok=report.ok,
        duration_seconds=duration,
        report=report,
    )
