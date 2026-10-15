from __future__ import annotations

import datetime as dt

import httpx
import pytest

from fx_etl import extract


def test_normalise_timeseries(raw_timeseries):
    records = extract.normalise_timeseries(raw_timeseries)
    assert len(records) == 6
    assert {"rate_date", "base_currency", "quote_currency", "rate"} <= set(records[0])
    assert all(r["base_currency"] == "USD" for r in records)


def test_normalise_rejects_bad_payload():
    with pytest.raises(ValueError):
        extract.normalise_timeseries({"rates": {}})


def test_fetch_timeseries_with_mock_transport(raw_timeseries):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "2024-01-01..2024-01-03" in str(request.url)
        return httpx.Response(200, json=raw_timeseries)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    payload = extract.fetch_timeseries(
        client,
        base_url="https://example.test",
        start=dt.date(2024, 1, 1),
        end=dt.date(2024, 1, 3),
        base_currency="USD",
        symbols=["EUR", "GBP"],
    )
    assert payload["base"] == "USD"


def test_fetch_retries_then_succeeds(raw_timeseries):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=raw_timeseries)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    payload = extract.fetch_timeseries(
        client, "https://example.test", dt.date(2024, 1, 1), dt.date(2024, 1, 3),
        "USD", ["EUR"], max_retries=5,
    )
    assert payload["base"] == "USD"
    assert calls["n"] == 3


def test_start_after_end_raises():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(ValueError):
        extract.fetch_timeseries(
            client, "https://example.test", dt.date(2024, 1, 5), dt.date(2024, 1, 1),
            "USD", ["EUR"],
        )


def test_load_records_from_csv(tmp_path):
    csv = tmp_path / "rates.csv"
    csv.write_text(
        "rate_date,base_currency,quote_currency,rate\n"
        "2024-01-01,USD,EUR,0.9\n"
    )
    records = extract.load_records_from_csv(str(csv))
    assert len(records) == 1
    assert records[0]["quote_currency"] == "EUR"
