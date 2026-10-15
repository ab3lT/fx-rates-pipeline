from __future__ import annotations

from fx_etl.config import Settings


def test_symbols_accept_comma_separated_env(monkeypatch):
    monkeypatch.setenv("FX_SYMBOLS", "eur, gbp,JPY")
    assert Settings().symbols == ["EUR", "GBP", "JPY"]
