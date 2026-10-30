"""Which forecast could the buyer actually see when they had to decide?

The rule, for one delivery day D and each target time T inside D:

    take the forecast for T with the LATEST publish_time that is <= the decision cutoff.

The cutoff is a clock time (cutoff_local, e.g. 09:00) on the day BEFORE D, in the market's
timezone (e.g. Europe/London). Forecasts published after the cutoff are never used, even if
they are newer, because the buyer could not have seen them (look-ahead bias).

Pure functions: no database, no HTTP, no global settings. Everything is passed in.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

REQUIRED_COLUMNS = ("start_time", "publish_time", "generation_mw")


def decision_cutoff(delivery_date: date, cutoff_local: time, tz: ZoneInfo) -> datetime:
    """The cutoff instant (UTC) for a delivery day: cutoff_local on the previous day."""
    local = datetime.combine(delivery_date - timedelta(days=1), cutoff_local, tzinfo=tz)
    return local.astimezone(UTC)


def delivery_window(delivery_date: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[start, end) of the delivery day as UTC instants, using the local calendar day."""
    start = datetime.combine(delivery_date, time(0, 0), tzinfo=tz)
    end = datetime.combine(delivery_date + timedelta(days=1), time(0, 0), tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def _check_frame(forecasts: pd.DataFrame) -> None:
    missing = [name for name in REQUIRED_COLUMNS if name not in forecasts.columns]
    if missing:
        raise ValueError(f"forecasts is missing columns: {missing}")
    for name in ("start_time", "publish_time"):
        if not isinstance(forecasts[name].dtype, pd.DatetimeTZDtype):
            raise ValueError(f"{name} must be timezone-aware datetimes")


def select_forecasts(
    forecasts: pd.DataFrame,
    delivery_date: date,
    cutoff_local: time,
    tz: ZoneInfo,
) -> pd.DataFrame:
    """The decision-time forecast for every target time in the delivery day.

    Input columns: start_time, publish_time (timezone-aware), generation_mw.
    Output columns: start_time, publish_time, generation_mw, horizon_hours,
    one row per start_time, sorted by start_time. Targets with no forecast known at the
    cutoff are simply absent: nothing is filled in or guessed.
    """
    _check_frame(forecasts)
    cutoff = decision_cutoff(delivery_date, cutoff_local, tz)
    window_start, window_end = delivery_window(delivery_date, tz)

    in_delivery_day = (forecasts["start_time"] >= window_start) & (
        forecasts["start_time"] < window_end
    )
    # Inclusive: a forecast published exactly AT the cutoff was visible to the buyer.
    known_at_cutoff = forecasts["publish_time"] <= cutoff
    candidates = forecasts[in_delivery_day & known_at_cutoff]

    latest = candidates.sort_values(["start_time", "publish_time"]).drop_duplicates(
        "start_time", keep="last"
    )
    horizon = (latest["start_time"] - latest["publish_time"]).dt.total_seconds() / 3600
    result = latest.assign(horizon_hours=horizon).reset_index(drop=True)
    return result[["start_time", "publish_time", "generation_mw", "horizon_hours"]]
