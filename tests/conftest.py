"""Shared test fixtures and import-path setup."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the src/ layout importable without installing the package.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402


@pytest.fixture
def raw_timeseries() -> dict:
    return {
        "base": "USD",
        "start_date": "2024-01-01",
        "end_date": "2024-01-03",
        "rates": {
            "2024-01-01": {"EUR": 0.90, "GBP": 0.78},
            "2024-01-02": {"EUR": 0.99, "GBP": 0.79},
            "2024-01-03": {"EUR": 0.91, "GBP": 0.80},
        },
    }
