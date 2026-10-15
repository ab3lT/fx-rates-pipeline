"""Transform stage: clean raw records and derive metrics with pandas."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .logging_config import get_logger

logger = get_logger(__name__)

_COLUMNS = ["rate_date", "base_currency", "quote_currency", "rate"]


def to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a typed DataFrame from raw record dicts."""
    frame = pd.DataFrame(records, columns=_COLUMNS)
    if frame.empty:
        return frame

    frame["rate_date"] = pd.to_datetime(frame["rate_date"], errors="coerce").dt.date
    frame["base_currency"] = frame["base_currency"].astype("string").str.strip().str.upper()
    frame["quote_currency"] = frame["quote_currency"].astype("string").str.strip().str.upper()
    frame["rate"] = pd.to_numeric(frame["rate"], errors="coerce")
    return frame


def clean(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop unusable rows, remove duplicates, and sort deterministically."""
    if frame.empty:
        return frame

    before = len(frame)
    frame = frame.dropna(subset=["rate_date", "quote_currency", "rate"])
    frame = frame[frame["rate"] > 0]
    frame = frame.drop_duplicates(
        subset=["rate_date", "base_currency", "quote_currency"], keep="last"
    )
    frame = frame.sort_values(
        ["quote_currency", "rate_date"], kind="stable"
    ).reset_index(drop=True)
    logger.info("clean kept=%d dropped=%d", len(frame), before - len(frame))
    return frame


def add_derived_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the day-on-day percentage change per currency pair."""
    if frame.empty:
        frame["pct_change"] = pd.Series(dtype="float64")
        return frame

    frame = frame.copy()
    frame["pct_change"] = (
        frame.groupby("quote_currency", sort=False)["rate"].pct_change() * 100.0
    )
    frame["pct_change"] = frame["pct_change"].round(4)
    return frame


def transform(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Run the full transform: typed frame, clean, derive metrics."""
    frame = to_frame(records)
    frame = clean(frame)
    frame = add_derived_metrics(frame)
    return frame
