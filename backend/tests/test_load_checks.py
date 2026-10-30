"""Tests for the data-gap checks that run after every ingestion."""

import importlib.util
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

from app.domain.models import ActualPoint, ForecastPoint

HALF_HOUR = timedelta(minutes=30)


def _load_script():
    # scripts/ is not a package, so load the file by path.
    path = Path(__file__).resolve().parents[1] / "scripts" / "load_data.py"
    spec = importlib.util.spec_from_file_location("load_data", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


load_data = _load_script()
DAY = date(2026, 1, 5)


def full_day_of_actuals(day: date) -> list[ActualPoint]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return [ActualPoint(start_time=start + i * HALF_HOUR, generation_mw=1000.0) for i in range(48)]


def forecast(published: datetime) -> ForecastPoint:
    return ForecastPoint(
        start_time=datetime(2026, 1, 10, tzinfo=UTC),
        publish_time=published,
        generation_mw=5000.0,
    )


def test_complete_day_has_no_missing_half_hours() -> None:
    assert load_data.missing_half_hours(full_day_of_actuals(DAY), DAY, DAY) == []


def test_one_missing_half_hour_is_reported() -> None:
    points = full_day_of_actuals(DAY)
    removed = points.pop(10)
    assert load_data.missing_half_hours(points, DAY, DAY) == [removed.start_time]


def test_a_day_with_no_data_is_all_missing() -> None:
    assert len(load_data.missing_half_hours([], DAY, DAY)) == 48


def test_window_covers_every_day_in_the_range() -> None:
    points = full_day_of_actuals(DAY)
    missing = load_data.missing_half_hours(points, DAY, DAY + timedelta(days=1))
    assert len(missing) == 48


def test_days_without_forecasts_finds_the_gap() -> None:
    points = [
        forecast(datetime(2026, 1, 5, 12, tzinfo=UTC)),
        forecast(datetime(2026, 1, 7, 12, tzinfo=UTC)),
    ]
    assert load_data.days_without_forecasts(points, date(2026, 1, 5), date(2026, 1, 7)) == [
        date(2026, 1, 6)
    ]


def test_publish_day_is_judged_in_utc() -> None:
    plus_one = timezone(timedelta(hours=1))
    # 00:30 at +01:00 is 23:30 UTC on the previous day.
    points = [forecast(datetime(2026, 1, 6, 0, 30, tzinfo=plus_one))]
    missing = load_data.days_without_forecasts(points, date(2026, 1, 5), date(2026, 1, 6))
    assert missing == [date(2026, 1, 6)]


def test_no_forecasts_at_all_means_every_day_is_missing() -> None:
    missing = load_data.days_without_forecasts([], date(2026, 1, 5), date(2026, 1, 7))
    assert len(missing) == 3
