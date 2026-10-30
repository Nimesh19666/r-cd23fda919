"""Tests for the forecast-selection rule, using small handmade data."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.services.forecast_selection import decision_cutoff, delivery_window, select_forecasts

LONDON = ZoneInfo("Europe/London")
CUTOFF = time(9, 0)
DELIVERY = date(2026, 1, 5)  # winter: London time equals UTC


def frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Build a forecast table from (start_time, publish_time, generation_mw) tuples."""
    return pd.DataFrame(
        {
            "start_time": pd.to_datetime([r[0] for r in rows], utc=True),
            "publish_time": pd.to_datetime([r[1] for r in rows], utc=True),
            "generation_mw": [r[2] for r in rows],
        }
    )


def test_cutoff_is_morning_of_day_before_in_london_time() -> None:
    assert decision_cutoff(DELIVERY, CUTOFF, LONDON) == datetime(2026, 1, 4, 9, 0, tzinfo=UTC)


def test_cutoff_follows_london_clock_in_summer() -> None:
    # 09:00 BST is 08:00 UTC
    cutoff = decision_cutoff(date(2026, 7, 15), CUTOFF, LONDON)
    assert cutoff == datetime(2026, 7, 14, 8, 0, tzinfo=UTC)


def test_delivery_window_winter() -> None:
    start, end = delivery_window(DELIVERY, LONDON)
    assert start == datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 1, 6, 0, 0, tzinfo=UTC)


def test_delivery_window_summer() -> None:
    start, end = delivery_window(date(2026, 7, 15), LONDON)
    assert start == datetime(2026, 7, 14, 23, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 15, 23, 0, tzinfo=UTC)


def test_picks_latest_forecast_published_at_or_before_cutoff() -> None:
    target = "2026-01-05T10:00Z"
    forecasts = frame(
        [
            (target, "2026-01-04T06:00Z", 100.0),
            (target, "2026-01-04T08:30Z", 200.0),
            (target, "2026-01-04T09:00Z", 300.0),  # exactly at the cutoff: still known
            (target, "2026-01-04T09:30Z", 400.0),  # after the cutoff: not known yet
        ]
    )
    result = select_forecasts(forecasts, DELIVERY, CUTOFF, LONDON)
    assert len(result) == 1
    assert result.loc[0, "generation_mw"] == 300.0
    assert result.loc[0, "publish_time"] == pd.Timestamp("2026-01-04T09:00Z")


def test_forecasts_published_after_cutoff_are_never_used() -> None:
    target = "2026-01-05T10:00Z"
    forecasts = frame(
        [
            (target, "2026-01-04T09:01Z", 500.0),  # one minute after the cutoff
            (target, "2026-01-05T23:00Z", 600.0),  # published after the target time itself
        ]
    )
    assert select_forecasts(forecasts, DELIVERY, CUTOFF, LONDON).empty


def test_each_target_gets_its_own_latest_forecast() -> None:
    forecasts = frame(
        [
            ("2026-01-05T10:00Z", "2026-01-04T07:30Z", 111.0),
            ("2026-01-05T10:00Z", "2026-01-04T08:30Z", 222.0),
            ("2026-01-05T11:00Z", "2026-01-04T07:30Z", 333.0),
        ]
    )
    result = select_forecasts(forecasts, DELIVERY, CUTOFF, LONDON)
    assert result["generation_mw"].tolist() == [222.0, 333.0]


def test_only_targets_inside_the_delivery_day_are_returned() -> None:
    published = "2026-01-04T08:00Z"
    forecasts = frame(
        [
            ("2026-01-04T23:00Z", published, 1.0),  # day before
            ("2026-01-05T00:00Z", published, 2.0),  # first moment of the delivery day
            ("2026-01-05T23:00Z", published, 3.0),  # last hour of the delivery day
            ("2026-01-06T00:00Z", published, 4.0),  # next day
        ]
    )
    result = select_forecasts(forecasts, DELIVERY, CUTOFF, LONDON)
    assert result["generation_mw"].tolist() == [2.0, 3.0]


def test_horizon_is_hours_between_publish_and_target() -> None:
    forecasts = frame([("2026-01-05T10:00Z", "2026-01-04T08:00Z", 1.0)])
    result = select_forecasts(forecasts, DELIVERY, CUTOFF, LONDON)
    assert result.loc[0, "horizon_hours"] == 26.0


def test_summer_uses_london_clock_for_cutoff_and_delivery_day() -> None:
    delivery = date(2026, 7, 15)  # London is UTC+1: the day starts 14 Jul 23:00 UTC
    forecasts = frame(
        [
            ("2026-07-14T23:00Z", "2026-07-14T07:59Z", 10.0),  # before the 08:00Z cutoff
            ("2026-07-14T23:00Z", "2026-07-14T08:30Z", 20.0),  # after the cutoff: ignored
            ("2026-07-15T23:00Z", "2026-07-14T07:00Z", 30.0),  # belongs to 16 July locally
        ]
    )
    result = select_forecasts(forecasts, delivery, CUTOFF, LONDON)
    assert result["generation_mw"].tolist() == [10.0]


def test_naive_timestamps_are_rejected() -> None:
    forecasts = pd.DataFrame(
        {
            "start_time": pd.to_datetime(["2026-01-05T10:00"]),
            "publish_time": pd.to_datetime(["2026-01-04T08:00"]),
            "generation_mw": [1.0],
        }
    )
    with pytest.raises(ValueError, match="timezone"):
        select_forecasts(forecasts, DELIVERY, CUTOFF, LONDON)


def test_missing_columns_are_rejected() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        select_forecasts(pd.DataFrame({"start_time": []}), DELIVERY, CUTOFF, LONDON)
