"""Application service: loads data, runs the pure calculations, shapes API responses."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from app.schemas.api import (
    AccuracyResponse,
    ActualPointOut,
    DecisionPoint,
    DecisionResponse,
    ErrorSummaryOut,
    GroupSummaryOut,
    HealthResponse,
    MetaResponse,
)
from app.services.data_source import DataSource
from app.services.forecast_selection import delivery_window
from app.services.metrics import ErrorSummary
from app.services.reports import AccuracyReport, build_accuracy_report, build_decision_view

ERROR_DEFINITION = (
    "error = forecast - actual. Positive means the forecast was too high (over-forecast); "
    "negative means it was too low."
)

RANGE_NOTE = (
    "Middle 80% of forecast errors in the January 2026 backtest. Computed in-sample, so it "
    "describes the past and is not a guarantee."
)

NOTES = [
    "Data: Elexon BMRS only. Actuals are FUELHH (fuel type WIND); forecasts are WINDFOR.",
    "Decision rule: for each target time, the latest forecast published at or before the "
    "cutoff on the day before delivery. Later forecasts were not visible to the buyer.",
    "Forecasts are hourly and actuals half-hourly, so they are compared only at timestamps "
    "where both exist.",
    "Forecasts published after their target time are stored but excluded from every calculation.",
    "In the January 2026 backtest the forecast was higher than actual wind on average (see "
    "bias). FUELHH wind may not cover all the wind that WINDFOR forecasts; this difference "
    "in scope is unverified.",
    "The expected range is the middle 80% of January 2026 backtest errors. It is computed "
    "in-sample, so it describes the past and is not a guarantee.",
    "Times are UTC. Delivery days and the cutoff follow the local market clock.",
]


class DateOutOfRangeError(ValueError):
    """The requested delivery date is outside the scope of the data."""


@dataclass(frozen=True)
class MarketConfig:
    cutoff_local: time
    tz: ZoneInfo
    decision_start_date: date
    decision_end_date: date

    @property
    def first_delivery_date(self) -> date:
        return self.decision_start_date + timedelta(days=1)

    @property
    def last_delivery_date(self) -> date:
        return self.decision_end_date + timedelta(days=1)


def _clean(value: Any) -> Any:
    """Turn NaN into None so the JSON stays valid."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): _clean(val) for key, val in row.items()} for row in frame.to_dict("records")]


def _groups(frame: pd.DataFrame, label: Callable[[Any], str]) -> list[GroupSummaryOut]:
    groups = []
    for row in _records(frame):
        group = row.pop("group")
        groups.append(GroupSummaryOut(label=label(group), **row))
    return groups


def _expected_range(
    forecast_mw: float, backtest: ErrorSummary
) -> tuple[float | None, float | None]:
    """actual = forecast - error, so the middle 80% of past errors bounds the actual wind."""
    if backtest.p10_error_mw is None or backtest.p90_error_mw is None:
        return None, None
    low = max(0.0, forecast_mw - backtest.p90_error_mw)
    high = max(0.0, forecast_mw - backtest.p10_error_mw)
    return low, high


class ReportService:
    def __init__(self, source: DataSource, config: MarketConfig) -> None:
        self._source = source
        self._config = config
        self._report: AccuracyReport | None = None
        self._lock = threading.Lock()

    def _check_delivery_date(self, delivery_date: date) -> None:
        first, last = self._config.first_delivery_date, self._config.last_delivery_date
        if not first <= delivery_date <= last:
            raise DateOutOfRangeError(f"delivery_date must be between {first} and {last}")

    def _accuracy_report(self) -> AccuracyReport:
        """Computed once, then cached (the data is static after ingestion)."""
        with self._lock:
            if self._report is None:
                config = self._config
                first, last = config.first_delivery_date, config.last_delivery_date
                start, _ = delivery_window(first, config.tz)
                _, end = delivery_window(last, config.tz)
                forecasts = self._source.load_forecasts(start, end)
                actuals = self._source.load_actuals(start, end)
                self._report = build_accuracy_report(
                    forecasts, actuals, first, last, config.cutoff_local, config.tz
                )
            return self._report

    def decision(self, delivery_date: date) -> DecisionResponse:
        self._check_delivery_date(delivery_date)
        config = self._config
        start, end = delivery_window(delivery_date, config.tz)
        forecasts = self._source.load_forecasts(start, end)
        actuals = self._source.load_actuals(start, end)
        view = build_decision_view(
            forecasts, actuals, delivery_date, config.cutoff_local, config.tz
        )

        backtest = self._accuracy_report().summary
        points = []
        for row in _records(view.comparison):
            low, high = _expected_range(row["forecast_mw"], backtest)
            points.append(DecisionPoint(**row, range_low_mw=low, range_high_mw=high))
        actual_points = [
            ActualPointOut(start_time=row["start_time"], actual_mw=row["generation_mw"])
            for row in _records(view.actuals)
        ]
        return DecisionResponse(
            delivery_date=delivery_date,
            cutoff_utc=view.cutoff_utc,
            points=points,
            actuals=actual_points,
            summary=ErrorSummaryOut.model_validate(asdict(view.summary)),
            range_note=RANGE_NOTE,
        )

    def accuracy(self) -> AccuracyResponse:
        report = self._accuracy_report()
        config = self._config
        return AccuracyResponse(
            first_delivery_date=report.first_delivery_date,
            last_delivery_date=report.last_delivery_date,
            cutoff_local=config.cutoff_local.strftime("%H:%M"),
            timezone=str(config.tz),
            summary=ErrorSummaryOut.model_validate(asdict(report.summary)),
            by_day=_groups(report.by_day, lambda group: group.isoformat()),
            by_hour=_groups(report.by_hour, lambda group: f"{int(group):02d}"),
            by_horizon=_groups(report.by_horizon, str),
            n_published_after_target=report.n_published_after_target,
        )

    def meta(self) -> MetaResponse:
        actuals_last, forecasts_last = self._source.freshness()
        config = self._config
        return MetaResponse(
            cutoff_local=config.cutoff_local.strftime("%H:%M"),
            timezone=str(config.tz),
            decision_start_date=config.decision_start_date,
            decision_end_date=config.decision_end_date,
            first_delivery_date=config.first_delivery_date,
            last_delivery_date=config.last_delivery_date,
            error_definition=ERROR_DEFINITION,
            notes=NOTES,
            actuals_last_time=actuals_last,
            forecasts_last_publish_time=forecasts_last,
        )

    def health(self) -> HealthResponse:
        ok = self._source.ping()
        return HealthResponse(status="ok" if ok else "degraded", database_ok=ok)
