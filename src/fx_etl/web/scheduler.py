"""Long-running scheduler: backfill history once, then run the pipeline on an interval.

    python -m fx_etl.web.scheduler

Kept as its own process (not inside the web workers) so that scaling the web
tier never multiplies scheduled runs.
"""

from __future__ import annotations

import datetime as dt
import signal
import threading

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import load
from ..config import get_settings
from ..logging_config import configure_logging, get_logger
from ..models import FxRate
from .runs import RunInProgress, tracked_run

logger = get_logger(__name__)


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = load.get_engine(settings.database_url)
    load.init_db(engine)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    with Session(engine) as session:
        has_data = session.scalar(select(func.count(FxRate.id))) or 0
    if not has_data and settings.backfill_days > 0:
        end = dt.date.today()
        start = end - dt.timedelta(days=settings.backfill_days)
        logger.info("empty database, backfilling start=%s end=%s", start, end)
        tracked_run(settings, engine, trigger="backfill", start=start, end=end)

    interval = max(settings.schedule_hours, 0.1) * 3600
    logger.info("scheduler started interval_hours=%s", settings.schedule_hours)
    while not stop.is_set():
        try:
            tracked_run(settings, engine, trigger="schedule")
        except RunInProgress:
            logger.warning("skipped scheduled run: another run in progress")
        stop.wait(interval)

    logger.info("scheduler stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
