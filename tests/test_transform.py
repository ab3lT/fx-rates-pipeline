from __future__ import annotations

import datetime as dt

from fx_etl import extract, transform


def test_to_frame_types(raw_timeseries):
    records = extract.normalise_timeseries(raw_timeseries)
    frame = transform.to_frame(records)
    assert len(frame) == 6
    assert isinstance(frame["rate_date"].iloc[0], dt.date)
    assert frame["quote_currency"].str.isupper().all()


def test_clean_drops_bad_rows():
    records = [
        {"rate_date": "2024-01-01", "base_currency": "USD", "quote_currency": "EUR", "rate": 0.9},
        {"rate_date": "2024-01-01", "base_currency": "USD", "quote_currency": "GBP", "rate": -1},
        {"rate_date": None, "base_currency": "USD", "quote_currency": "JPY", "rate": 150},
    ]
    frame = transform.clean(transform.to_frame(records))
    assert len(frame) == 1
    assert frame["quote_currency"].iloc[0] == "EUR"


def test_clean_dedupes_keeping_last():
    records = [
        {"rate_date": "2024-01-01", "base_currency": "USD", "quote_currency": "EUR", "rate": 0.90},
        {"rate_date": "2024-01-01", "base_currency": "USD", "quote_currency": "EUR", "rate": 0.95},
    ]
    frame = transform.clean(transform.to_frame(records))
    assert len(frame) == 1
    assert frame["rate"].iloc[0] == 0.95


def test_pct_change_is_per_pair(raw_timeseries):
    records = extract.normalise_timeseries(raw_timeseries)
    frame = transform.transform(records)
    eur = frame[frame["quote_currency"] == "EUR"].reset_index(drop=True)
    # First day has no prior value.
    assert eur["pct_change"].isna().iloc[0]
    # 0.90 -> 0.99 is a 10% rise.
    assert abs(eur["pct_change"].iloc[1] - 10.0) < 1e-6


def test_empty_input_is_safe():
    frame = transform.transform([])
    assert frame.empty
    assert "pct_change" in frame.columns
