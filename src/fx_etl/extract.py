"""Extract stage: pull raw rates from the API or from a local CSV file.

The API returns a time series shaped like:

    {
      "base": "USD",
      "start_date": "2024-01-01",
      "end_date": "2024-01-03",
      "rates": {
        "2024-01-01": {"EUR": 0.90, "GBP": 0.78},
        "2024-01-02": {"EUR": 0.91, "GBP": 0.79}
      }
    }

Both sources are normalised into the same list of flat record dicts so the
transform stage does not care where the data came from.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
import pandas as pd
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .logging_config import get_logger

logger = get_logger(__name__)

# Errors worth retrying: transient network issues and 5xx responses.
_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


def _make_retrying_fetch(max_retries: int):
    @retry(
        reraise=True,
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=0.5, max=10),
        retry=retry_if_exception_type(_RETRYABLE),
    )
    def _fetch(client: httpx.Client, url: str, params: dict[str, Any]) -> dict[str, Any]:
        logger.info("fetch url=%s params=%s", url, params)
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    return _fetch


def fetch_timeseries(
    client: httpx.Client,
    base_url: str,
    start: dt.date,
    end: dt.date,
    base_currency: str,
    symbols: list[str],
    max_retries: int = 4,
) -> dict[str, Any]:
    """Fetch the raw time-series payload for a date range."""
    if start > end:
        raise ValueError(f"start {start} is after end {end}")

    url = f"{base_url.rstrip('/')}/{start.isoformat()}..{end.isoformat()}"
    params = {"base": base_currency, "symbols": ",".join(symbols)}
    fetch = _make_retrying_fetch(max_retries)
    return fetch(client, url, params)


def normalise_timeseries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the nested API payload into a list of record dicts."""
    base = payload.get("base")
    rates = payload.get("rates", {})
    if not base or not isinstance(rates, dict):
        raise ValueError("payload missing 'base' or 'rates'")

    records: list[dict[str, Any]] = []
    for date_str, quotes in rates.items():
        for quote_currency, rate in quotes.items():
            records.append(
                {
                    "rate_date": date_str,
                    "base_currency": base,
                    "quote_currency": quote_currency,
                    "rate": rate,
                }
            )
    logger.info("normalised records=%d", len(records))
    return records


def load_records_from_csv(path: str) -> list[dict[str, Any]]:
    """Read records from a CSV file with columns:
    rate_date, base_currency, quote_currency, rate
    """
    frame = pd.read_csv(path)
    expected = {"rate_date", "base_currency", "quote_currency", "rate"}
    missing = expected - set(frame.columns)
    if missing:
        raise ValueError(f"csv missing columns: {sorted(missing)}")
    logger.info("read csv path=%s rows=%d", path, len(frame))
    return frame[list(expected)].to_dict(orient="records")
