from __future__ import annotations

from sqlalchemy import func, select

from fx_etl import extract, load, transform
from fx_etl.models import FxRate


def _frame(raw_timeseries):
    return transform.transform(extract.normalise_timeseries(raw_timeseries))


def test_upsert_is_idempotent(raw_timeseries):
    engine = load.get_engine("sqlite:///:memory:")
    load.init_db(engine)
    frame = _frame(raw_timeseries)

    first = load.upsert_frame(engine, frame)
    second = load.upsert_frame(engine, frame)
    assert first == second == len(frame)

    with engine.begin() as conn:
        total = conn.execute(select(func.count()).select_from(FxRate)).scalar_one()
    # Re-running must not create duplicate rows.
    assert total == len(frame)


def test_upsert_updates_rate_on_conflict(raw_timeseries):
    engine = load.get_engine("sqlite:///:memory:")
    load.init_db(engine)

    frame = _frame(raw_timeseries)
    load.upsert_frame(engine, frame)

    changed = frame.copy()
    changed.loc[changed.index[0], "rate"] = 1.2345
    load.upsert_frame(engine, changed)

    row = changed.iloc[0]
    with engine.begin() as conn:
        stored = conn.execute(
            select(FxRate.rate).where(
                FxRate.rate_date == row["rate_date"],
                FxRate.quote_currency == row["quote_currency"],
            )
        ).scalar_one()
    assert abs(stored - 1.2345) < 1e-9


def test_empty_frame_loads_nothing():
    engine = load.get_engine("sqlite:///:memory:")
    load.init_db(engine)
    assert load.upsert_frame(engine, transform.transform([])) == 0
