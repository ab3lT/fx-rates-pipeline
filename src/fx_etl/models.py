"""Database schema (SQLAlchemy) and the row-level validation schema (pydantic)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, field_validator
from sqlalchemy import (
    DateTime,
    Float,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class FxRate(Base):
    """One exchange rate for a (date, base, quote) triple."""

    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", "base_currency", "quote_currency", name="uq_fx_rate"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rate_date: Mapped[dt.date] = mapped_column(index=True)
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[float] = mapped_column(Float)
    pct_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FxRateRecord(BaseModel):
    """Validation schema for a single transformed record before it is loaded."""

    rate_date: dt.date
    base_currency: str
    quote_currency: str
    rate: float
    pct_change: float | None = None

    @field_validator("base_currency", "quote_currency")
    @classmethod
    def _valid_currency(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError(f"invalid currency code: {value!r}")
        return code

    @field_validator("rate")
    @classmethod
    def _positive_rate(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"rate must be positive, got {value}")
        return value
