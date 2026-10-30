"""Load wind data from Elexon into the database. Usage (from backend/, venv active):

    python scripts/load_data.py

Scope comes from settings: decisions made 1-31 Jan 2026 means delivery days 2 Jan - 1 Feb.
Actuals are fetched for 1 Jan - 1 Feb. Forecasts are fetched from 3 days before 1 Jan
(a forecast can be published up to ~66 hours ahead) to 1 Feb. The script checks the data
for gaps BEFORE writing anything, and is safe to re-run.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from app.clients.elexon import ElexonClient
from app.core.config import get_settings
from app.db import get_engine
from app.domain.models import ActualPoint, ForecastPoint
from app.repositories import wind

FORECAST_LOOKBACK_DAYS = 3
HALF_HOUR = timedelta(minutes=30)
HALF_HOURS_PER_DAY = 48  # true for UTC days; January has no clock change


def missing_half_hours(
    points: Sequence[ActualPoint], first_day: date, last_day: date
) -> list[datetime]:
    """Half-hours between the two days (inclusive) that have no actual."""
    start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=UTC)
    total = ((last_day - first_day).days + 1) * HALF_HOURS_PER_DAY
    expected = {start + i * HALF_HOUR for i in range(total)}
    return sorted(expected - {p.start_time for p in points})


def days_without_forecasts(
    points: Sequence[ForecastPoint], first_day: date, last_day: date
) -> list[date]:
    """Days in the window on which no forecast was published at all."""
    seen = {p.publish_time.astimezone(UTC).date() for p in points}
    total_days = (last_day - first_day).days + 1
    return [d for d in (first_day + timedelta(days=i) for i in range(total_days)) if d not in seen]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = get_settings()
    last_day = settings.decision_end_date + timedelta(days=1)
    actuals_first = settings.decision_start_date
    forecasts_first = settings.decision_start_date - timedelta(days=FORECAST_LOOKBACK_DAYS)
    print(f"Actuals:   settlement days {actuals_first} to {last_day}")
    print(f"Forecasts: published days  {forecasts_first} to {last_day}")

    with ElexonClient() as client:
        actuals = client.fetch_actuals(actuals_first, last_day)
        forecasts = client.fetch_forecasts(forecasts_first, last_day)

    expected_actuals = ((last_day - actuals_first).days + 1) * HALF_HOURS_PER_DAY
    print(
        f"\nFetched {len(actuals)} actuals (expected {expected_actuals}), "
        f"{len(forecasts)} forecasts"
    )

    problems: list[str] = []
    gaps = missing_half_hours(actuals, actuals_first, last_day)
    if gaps:
        problems.append(f"{len(gaps)} half-hours missing from actuals, first: {gaps[0]}")
    empty_days = days_without_forecasts(forecasts, forecasts_first, last_day)
    if empty_days:
        problems.append(f"no forecasts published on: {[d.isoformat() for d in empty_days]}")
    if problems:
        print("\nDATA CHECK FAILED, nothing written:")
        for problem in problems:
            print(" -", problem)
        return 1
    print("Data checks passed: no gaps in actuals, forecasts exist for every day.")

    engine = get_engine()
    wind.upsert_actuals(engine, actuals)
    wind.upsert_forecasts(engine, forecasts)

    print("\nDatabase now contains:")
    for table, stats in wind.summary(engine).items():
        print(f"  {table}:")
        for key, value in stats.items():
            print(f"    {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
