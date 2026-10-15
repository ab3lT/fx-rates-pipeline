"""Command-line entry point.

Examples:
    python -m fx_etl.cli --start 2024-01-01 --end 2024-01-31
    python -m fx_etl.cli --source file --file data/seed_rates.csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from .config import get_settings
from .pipeline import run_pipeline
from .quality import DataQualityError


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FX rates ETL pipeline")
    parser.add_argument("--start", type=_parse_date, help="start date YYYY-MM-DD")
    parser.add_argument("--end", type=_parse_date, help="end date YYYY-MM-DD")
    parser.add_argument(
        "--source", choices=["api", "file"], default="api", help="where to read from"
    )
    parser.add_argument("--file", help="CSV path when --source file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    try:
        result = run_pipeline(
            settings=settings,
            start=args.start,
            end=args.end,
            source=args.source,
            file=args.file,
        )
    except DataQualityError as exc:
        print(f"PIPELINE FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        f"OK rows_loaded={result.rows_loaded} "
        f"quality_ok={result.quality_ok} "
        f"duration={result.duration_seconds:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
