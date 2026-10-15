from __future__ import annotations

from fx_etl import extract, quality, transform


def _good_frame(raw_timeseries):
    return transform.transform(extract.normalise_timeseries(raw_timeseries))


def test_good_frame_passes(raw_timeseries):
    report = quality.run_checks(_good_frame(raw_timeseries), expected_symbols=["EUR", "GBP"])
    assert report.ok is True


def test_empty_frame_fails_critical():
    report = quality.run_checks(transform.transform([]), expected_symbols=["EUR"])
    assert report.ok is False
    assert any(r.name == "non_empty" and not r.passed for r in report.results)


def test_missing_currency_is_warning_not_critical(raw_timeseries):
    report = quality.run_checks(_good_frame(raw_timeseries), expected_symbols=["EUR", "GBP", "JPY"])
    # JPY is missing, but that is a warning so the report still passes.
    assert report.ok is True
    missing_check = next(r for r in report.results if r.name == "expected_currencies_present")
    assert missing_check.passed is False
    assert missing_check.critical is False


def test_negative_rate_fails_critical():
    records = [
        {"rate_date": "2024-01-01", "base_currency": "USD", "quote_currency": "EUR", "rate": 0.9},
    ]
    frame = transform.to_frame(records)
    frame.loc[0, "rate"] = -5  # inject a bad value after cleaning
    frame["pct_change"] = None
    report = quality.run_checks(frame)
    assert report.ok is False
