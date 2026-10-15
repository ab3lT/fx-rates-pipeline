"""Load stage: upsert transformed rows into the database.

The upsert is idempotent: re-running the pipeline for the same dates updates the
existing rows instead of creating duplicates. The ON CONFLICT clause is chosen
to match the active dialect, so the same code path works on both PostgreSQL and
SQLite.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .logging_config import get_logger
from .models import Base, FxRate, FxRateRecord

logger = get_logger(__name__)

_CONFLICT_COLS = ["rate_date", "base_currency", "quote_currency"]


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True)


_INIT_LOCK_ID = 724001  # arbitrary, app-wide key for pg_advisory_xact_lock


def init_db(engine: Engine) -> None:
    """Create tables if missing. Safe to call from several processes at once."""
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            # Web workers and the scheduler start together; without the lock their
            # concurrent CREATE TABLEs collide on Postgres' catalog.
            conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _INIT_LOCK_ID})
        Base.metadata.create_all(conn)


def _validate_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Validate each row through the pydantic schema before loading."""
    rows: list[dict[str, Any]] = []
    for raw in frame.to_dict(orient="records"):
        pct = raw.get("pct_change")
        if pct is not None and isinstance(pct, float) and math.isnan(pct):
            pct = None
        record = FxRateRecord(
            rate_date=raw["rate_date"],
            base_currency=raw["base_currency"],
            quote_currency=raw["quote_currency"],
            rate=raw["rate"],
            pct_change=pct,
        )
        rows.append(record.model_dump())
    return rows


def upsert_frame(engine: Engine, frame: pd.DataFrame) -> int:
    """Insert or update every row of the frame. Returns the number of rows sent."""
    if frame.empty:
        logger.info("upsert skipped: empty frame")
        return 0

    rows = _validate_rows(frame)
    dialect = engine.dialect.name

    if dialect == "postgresql":
        insert_stmt = pg_insert(FxRate).values(rows)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=_CONFLICT_COLS,
            set_={
                "rate": insert_stmt.excluded.rate,
                "pct_change": insert_stmt.excluded.pct_change,
            },
        )
    elif dialect == "sqlite":
        insert_stmt = sqlite_insert(FxRate).values(rows)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=_CONFLICT_COLS,
            set_={
                "rate": insert_stmt.excluded.rate,
                "pct_change": insert_stmt.excluded.pct_change,
            },
        )
    else:
        raise NotImplementedError(f"upsert not implemented for dialect {dialect!r}")

    with engine.begin() as conn:
        conn.execute(stmt)

    logger.info("upsert dialect=%s rows=%d", dialect, len(rows))
    return len(rows)
