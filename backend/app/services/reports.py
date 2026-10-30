"""Turns raw forecast and actual tables into the numbers the app shows. Pure functions.

Two views, deliberately kept separate:

  decision view     what the buyer could see at the cutoff for ONE delivery day, plus (as a
                    retrospective check) how it compared with what really happened.
  accuracy report   how wrong the decision-time forecasts were across many delivery days,
                    split by day and hour, plus error by forecast horizon using EVERY
                    forecast published before its target time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.services.forecast_selection import decision_cutoff, delivery_window, select_forecasts
from app.services.metrics import ErrorSummary, compare, summarise_by_group, summarise_errors

HORIZON_BINS = [0, 6, 12, 18, 24, 36, 48, math.inf]
HORIZON_LABELS = ["0-6h", "6-12h", "12-18h", "18-24h", "24-36h", "36-48h", "48h+"]


@dataclass(frozen=True)
class DecisionView:
    delivery_date: date
    cutoff_utc: datetime
    selected: pd.DataFrame  # known at the cutoff (includes publish_time, horizon_hours)
    actuals: pd.DataFrame  # what really happened that day (only known afterwards)
    comparison: pd.DataFrame  # selected forecasts joined to actuals, with errors
    summary: ErrorSummary


@dataclass(frozen=True)
class AccuracyReport:
    first_delivery_date: date
    last_delivery_date: date
    summary: ErrorSummary  # decision-time forecasts, all delivery days together
    by_day: pd.DataFrame
    by_hour: pd.DataFrame  # hour of day in the market timezone
    by_horizon: pd.DataFrame  # all forecasts published before their target time
    n_published_after_target: int  # rows excluded from by_horizon


def _days(first_day: date, last_day: date) -> list[date]:
    if first_day > last_day:
        raise ValueError("first_day must not be after last_day")
    return [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]


def build_decision_view(
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    delivery_date: date,
    cutoff_local: time,
    tz: ZoneInfo,
) -> DecisionView:
    selected = select_forecasts(forecasts, delivery_date, cutoff_local, tz)
    start, end = delivery_window(delivery_date, tz)
    day_actuals = actuals[(actuals["start_time"] >= start) & (actuals["start_time"] < end)]
    comparison = compare(selected, day_actuals)
    return DecisionView(
        delivery_date=delivery_date,
        cutoff_utc=decision_cutoff(delivery_date, cutoff_local, tz),
        selected=selected,
        actuals=day_actuals.reset_index(drop=True),
        comparison=comparison,
        summary=summarise_errors(comparison),
    )


def build_accuracy_report(
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    first_day: date,
    last_day: date,
    cutoff_local: time,
    tz: ZoneInfo,
) -> AccuracyReport:
    # 1. Decision-time forecasts for every delivery day in the range.
    days = _days(first_day, last_day)
    parts = [select_forecasts(forecasts, day, cutoff_local, tz) for day in days]
    non_empty = [part for part in parts if not part.empty]
    selected = pd.concat(non_empty, ignore_index=True) if non_empty else parts[-1]
    comparison = compare(selected, actuals)

    local_start = comparison["start_time"].dt.tz_convert(tz)
    by_day = summarise_by_group(comparison, local_start.dt.date)
    by_hour = summarise_by_group(comparison, local_start.dt.hour)

    # 2. Error against forecast horizon, using every forecast published before its target.
    window_start, _ = delivery_window(first_day, tz)
    _, window_end = delivery_window(last_day, tz)
    in_window = forecasts[
        (forecasts["start_time"] >= window_start) & (forecasts["start_time"] < window_end)
    ]
    usable = in_window[in_window["publish_time"] < in_window["start_time"]]
    horizon_comparison = compare(usable, actuals)
    buckets = pd.cut(
        horizon_comparison["horizon_hours"], bins=HORIZON_BINS, labels=HORIZON_LABELS, right=False
    )
    by_horizon = summarise_by_group(horizon_comparison, buckets)

    return AccuracyReport(
        first_delivery_date=first_day,
        last_delivery_date=last_day,
        summary=summarise_errors(comparison),
        by_day=by_day,
        by_hour=by_hour,
        by_horizon=by_horizon,
        n_published_after_target=len(in_window) - len(usable),
    )
