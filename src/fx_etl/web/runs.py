"""Run the pipeline and record every execution in the pipeline_runs table.

Both the scheduler and the dashboard's manual trigger go through tracked_run,
so the run history shown in the UI is a complete audit trail, including runs
that failed their quality checks.
"""

from __future__ import annotations

import datetime as dt
import threading
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from ..config import Settings
from ..logging_config import get_logger
from ..models import PipelineRun
from ..pipeline import run_pipeline
from ..quality import DataQualityError, QualityReport

logger = get_logger(__name__)

# One pipeline at a time per process; a second trigger is rejected, not queued.
_lock = threading.Lock()


class RunInProgress(RuntimeError):
    """Raised when a run is requested while another is still going."""


def _checks(report: QualityReport | None) -> list[dict[str, Any]] | None:
    if report is None:
        return None
    return [
        {"name": r.name, "passed": r.passed, "critical": r.critical, "detail": r.detail}
        for r in report.results
    ]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def tracked_run(
    settings: Settings,
    engine: Engine,
    trigger: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
    source: str = "api",
    file: str | None = None,
) -> PipelineRun:
    """Run the pipeline once and persist the outcome. Never raises on pipeline failure."""
    if not _lock.acquire(blocking=False):
        raise RunInProgress("a pipeline run is already in progress")

    try:
        end = end or dt.date.today()
        start = start or (end - dt.timedelta(days=7))
        run = PipelineRun(
            started_at=_now(),
            trigger=trigger,
            source=source,
            start_date=start,
            end_date=end,
            status="running",
            rows_loaded=0,
        )
        try:
            result = run_pipeline(settings=settings, start=start, end=end, source=source, file=file)
            run.status = "success" if all(r.passed for r in result.report.results) else "warning"
            run.rows_loaded = result.rows_loaded
            run.duration_seconds = round(result.duration_seconds, 3)
            run.checks = _checks(result.report)
        except DataQualityError as exc:
            run.status = "failed"
            run.error = str(exc)
            run.checks = _checks(exc.report)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded, then logged
            logger.exception("pipeline run failed trigger=%s", trigger)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"

        run.finished_at = _now()
        if run.duration_seconds is None:
            run.duration_seconds = round((run.finished_at - run.started_at).total_seconds(), 3)

        with Session(engine, expire_on_commit=False) as session:
            session.add(run)
            session.commit()
        logger.info("run recorded id=%s status=%s rows=%d", run.id, run.status, run.rows_loaded)
        return run
    finally:
        _lock.release()
