from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fx_etl import extract, load, transform
from fx_etl.config import Settings
from fx_etl.models import PipelineRun
from fx_etl.web import create_app
from fx_etl.web.runs import tracked_run


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        symbols=["EUR", "GBP"],
        admin_token="secret",
    )


@pytest.fixture
def app(settings, raw_timeseries):
    app = create_app(settings)
    engine = app.extensions["fx_engine"]
    frame = transform.transform(extract.normalise_timeseries(raw_timeseries))
    load.upsert_frame(engine, frame)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"FX Rates ETL" in response.data


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_summary(client):
    body = client.get("/api/summary").get_json()
    assert body["total_rows"] == 6
    assert body["quote_currencies"] == ["EUR", "GBP"]
    assert body["first_date"] == "2024-01-01"
    assert body["last_date"] == "2024-01-03"


def test_latest_returns_one_row_per_quote(client):
    body = client.get("/api/latest").get_json()
    assert [(r["quote_currency"], r["rate"]) for r in body] == [("EUR", 0.91), ("GBP", 0.80)]


def test_rates_series(client):
    body = client.get("/api/rates?quote=eur&days=30").get_json()
    assert body["quote_currency"] == "EUR"
    assert [p["date"] for p in body["points"]] == ["2024-01-01", "2024-01-02", "2024-01-03"]


def test_rates_rejects_bad_quote(client):
    assert client.get("/api/rates?quote=EURO").status_code == 400


def test_trigger_requires_token(client):
    assert client.post("/api/runs").status_code == 401
    assert client.post("/api/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_tracked_run_records_success(settings, app, tmp_path):
    csv = tmp_path / "rates.csv"
    csv.write_text(
        "rate_date,base_currency,quote_currency,rate\n"
        "2024-02-01,USD,EUR,0.92\n2024-02-01,USD,GBP,0.79\n"
    )
    engine = app.extensions["fx_engine"]
    run = tracked_run(settings, engine, trigger="manual", source="file", file=str(csv))

    assert run.status == "success"
    assert run.rows_loaded == 2
    assert {c["name"] for c in run.checks} >= {"non_empty", "no_duplicates"}

    runs = app.test_client().get("/api/runs").get_json()
    assert runs[0]["id"] == run.id


def test_tracked_run_records_failure(settings, app, tmp_path):
    csv = tmp_path / "empty.csv"
    csv.write_text("rate_date,base_currency,quote_currency,rate\n")
    engine = app.extensions["fx_engine"]
    run = tracked_run(settings, engine, trigger="manual", source="file", file=str(csv))

    assert run.status == "failed"
    assert "non_empty" in run.error
    with Session(engine) as session:
        assert session.scalar(select(func.count(PipelineRun.id))) == 1
