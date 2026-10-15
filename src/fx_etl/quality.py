"""Data quality checks that run between transform and load.

Each check returns a CheckResult. Critical failures stop the pipeline so bad
data never reaches the database; warnings are logged but allowed through.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CheckResult:
    name: str
    passed: bool
    critical: bool
    detail: str = ""


@dataclass
class QualityReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True unless a critical check failed."""
        return all(r.passed for r in self.results if r.critical)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)
        level = logging.INFO if result.passed else (
            logging.ERROR if result.critical else logging.WARNING
        )
        logger.log(
            level,
            "check name=%s passed=%s critical=%s detail=%s",
            result.name,
            result.passed,
            result.critical,
            result.detail,
        )


class DataQualityError(RuntimeError):
    """Raised when a critical data quality check fails."""

    def __init__(self, message: str, report: QualityReport | None = None) -> None:
        super().__init__(message)
        self.report = report


def run_checks(frame: pd.DataFrame, expected_symbols: list[str] | None = None) -> QualityReport:
    """Run all checks against a transformed frame and return a report."""
    report = QualityReport()

    # Critical: there is data at all.
    report.add(
        CheckResult(
            name="non_empty",
            passed=not frame.empty,
            critical=True,
            detail=f"rows={len(frame)}",
        )
    )
    if frame.empty:
        return report

    # Critical: no nulls in key columns.
    key_cols = ["rate_date", "base_currency", "quote_currency", "rate"]
    null_counts = frame[key_cols].isna().sum().to_dict()
    report.add(
        CheckResult(
            name="no_nulls_in_key_columns",
            passed=all(v == 0 for v in null_counts.values()),
            critical=True,
            detail=str(null_counts),
        )
    )

    # Critical: all rates strictly positive.
    bad_rates = int((frame["rate"] <= 0).sum())
    report.add(
        CheckResult(
            name="rates_positive",
            passed=bad_rates == 0,
            critical=True,
            detail=f"non_positive={bad_rates}",
        )
    )

    # Critical: no duplicate (date, base, quote) triples.
    dup = int(
        frame.duplicated(subset=["rate_date", "base_currency", "quote_currency"]).sum()
    )
    report.add(
        CheckResult(
            name="no_duplicates",
            passed=dup == 0,
            critical=True,
            detail=f"duplicates={dup}",
        )
    )

    # Warning: all requested currencies are present.
    if expected_symbols:
        present = set(frame["quote_currency"].unique())
        missing = sorted(set(s.upper() for s in expected_symbols) - present)
        report.add(
            CheckResult(
                name="expected_currencies_present",
                passed=not missing,
                critical=False,
                detail=f"missing={missing}",
            )
        )

    # Warning: flag implausibly large daily moves (> 25%).
    if "pct_change" in frame.columns:
        pct = pd.to_numeric(frame["pct_change"], errors="coerce")
        extreme = int((pct.abs() > 25).sum())
        report.add(
            CheckResult(
                name="no_extreme_daily_moves",
                passed=extreme == 0,
                critical=False,
                detail=f"moves_over_25pct={extreme}",
            )
        )

    return report
