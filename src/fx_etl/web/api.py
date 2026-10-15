"""JSON API over the loaded rates and the pipeline run history."""

from __future__ import annotations

import datetime as dt
import hmac
import threading
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FxRate, PipelineRun
from .runs import RunInProgress, tracked_run

bp = Blueprint("api", __name__, url_prefix="/api")

_MAX_DAYS = 3650


def _session() -> Session:
    return Session(current_app.extensions["fx_engine"])


def _iso(value: dt.date | dt.datetime | None) -> str | None:
    if value is None:
        return None
    # SQLite drops tzinfo on read; timestamps are always written in UTC.
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.isoformat()


def _run_to_dict(run: PipelineRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "trigger": run.trigger,
        "source": run.source,
        "start_date": _iso(run.start_date),
        "end_date": _iso(run.end_date),
        "status": run.status,
        "rows_loaded": run.rows_loaded,
        "duration_seconds": run.duration_seconds,
        "checks": run.checks or [],
        "error": run.error,
    }


def _bad_request(message: str):
    return jsonify({"error": message}), 400


@bp.get("/health")
def health():
    with _session() as session:
        session.execute(select(1))
    return jsonify({"status": "ok"})


@bp.get("/summary")
def summary():
    """Headline numbers for the dashboard."""
    settings = current_app.config["FX_SETTINGS"]
    with _session() as session:
        total_rows, first_date, last_date = session.execute(
            select(func.count(FxRate.id), func.min(FxRate.rate_date), func.max(FxRate.rate_date))
        ).one()
        quotes = session.scalars(
            select(FxRate.quote_currency).distinct().order_by(FxRate.quote_currency)
        ).all()
        total_runs = session.scalar(select(func.count(PipelineRun.id))) or 0
        ok_runs = session.scalar(
            select(func.count(PipelineRun.id)).where(PipelineRun.status != "failed")
        ) or 0
        last_run = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
        ).first()

    return jsonify(
        {
            "base_currency": settings.base_currency,
            "quote_currencies": list(quotes),
            "configured_symbols": settings.symbols,
            "total_rows": total_rows,
            "first_date": _iso(first_date),
            "last_date": _iso(last_date),
            "total_runs": total_runs,
            "success_rate": round(ok_runs / total_runs * 100, 1) if total_runs else None,
            "last_run": _run_to_dict(last_run) if last_run else None,
            "schedule_hours": settings.schedule_hours,
        }
    )


@bp.get("/latest")
def latest():
    """Latest rate per quote currency, with the day-on-day change."""
    with _session() as session:
        latest_dates = (
            select(FxRate.quote_currency, func.max(FxRate.rate_date).label("d"))
            .group_by(FxRate.quote_currency)
            .subquery()
        )
        rows = session.scalars(
            select(FxRate)
            .join(
                latest_dates,
                (FxRate.quote_currency == latest_dates.c.quote_currency)
                & (FxRate.rate_date == latest_dates.c.d),
            )
            .order_by(FxRate.quote_currency)
        ).all()

    return jsonify(
        [
            {
                "rate_date": _iso(r.rate_date),
                "base_currency": r.base_currency,
                "quote_currency": r.quote_currency,
                "rate": r.rate,
                "pct_change": r.pct_change,
            }
            for r in rows
        ]
    )


@bp.get("/rates")
def rates():
    """Time series for one quote currency: ?quote=EUR&days=90."""
    quote = (request.args.get("quote") or "").strip().upper()
    if len(quote) != 3 or not quote.isalpha():
        return _bad_request("quote must be a 3-letter currency code")
    try:
        days = int(request.args.get("days", 90))
    except ValueError:
        return _bad_request("days must be an integer")
    days = max(1, min(days, _MAX_DAYS))

    with _session() as session:
        last = session.scalar(
            select(func.max(FxRate.rate_date)).where(FxRate.quote_currency == quote)
        )
        if last is None:
            return jsonify({"quote_currency": quote, "points": []})
        since = last - dt.timedelta(days=days)
        rows = session.scalars(
            select(FxRate)
            .where(FxRate.quote_currency == quote, FxRate.rate_date > since)
            .order_by(FxRate.rate_date)
        ).all()

    return jsonify(
        {
            "quote_currency": quote,
            "points": [
                {"date": _iso(r.rate_date), "rate": r.rate, "pct_change": r.pct_change}
                for r in rows
            ],
        }
    )


@bp.get("/runs")
def runs():
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
    except ValueError:
        return _bad_request("limit must be an integer")
    with _session() as session:
        rows = session.scalars(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        ).all()
    return jsonify([_run_to_dict(r) for r in rows])


@bp.post("/runs")
def trigger_run():
    """Start a pipeline run in the background. Requires the admin token."""
    settings = current_app.config["FX_SETTINGS"]
    token = settings.admin_token
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(supplied, token):
        return jsonify({"error": "unauthorised"}), 401

    body = request.get_json(silent=True) or {}
    try:
        start = dt.date.fromisoformat(body["start"]) if body.get("start") else None
        end = dt.date.fromisoformat(body["end"]) if body.get("end") else None
    except (TypeError, ValueError):
        return _bad_request("start and end must be YYYY-MM-DD")

    engine = current_app.extensions["fx_engine"]

    def _work() -> None:
        try:
            tracked_run(settings, engine, trigger="manual", start=start, end=end)
        except RunInProgress:
            pass

    threading.Thread(target=_work, daemon=True).start()
    return jsonify({"status": "started"}), 202


@bp.errorhandler(RunInProgress)
def _in_progress(exc: RunInProgress):
    return jsonify({"error": str(exc)}), 409
