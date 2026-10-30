"""All SQL for the wind tables. Nothing else in the app writes SQL."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any, TypeVar

import pandas as pd
from sqlalchemy import Engine, text

from app.domain.models import ActualPoint, ForecastPoint

BATCH_SIZE = 1000
ItemT = TypeVar("ItemT")

_UPSERT_ACTUALS = text(
    """
    INSERT INTO wind_actuals (start_time, generation_mw)
    VALUES (:start_time, :generation_mw)
    ON CONFLICT (start_time) DO UPDATE
    SET generation_mw = EXCLUDED.generation_mw, ingested_at = now()
    """
)

_UPSERT_FORECASTS = text(
    """
    INSERT INTO wind_forecasts (start_time, publish_time, generation_mw)
    VALUES (:start_time, :publish_time, :generation_mw)
    ON CONFLICT (start_time, publish_time) DO UPDATE
    SET generation_mw = EXCLUDED.generation_mw, ingested_at = now()
    """
)


def _batches(items: Sequence[ItemT], size: int) -> Iterator[Sequence[ItemT]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def upsert_actuals(engine: Engine, points: Sequence[ActualPoint]) -> int:
    """Insert or update actuals. Safe to re-run: existing rows are overwritten."""
    params = [{"start_time": p.start_time, "generation_mw": p.generation_mw} for p in points]
    with engine.begin() as conn:  # one transaction: all rows or none
        for batch in _batches(params, BATCH_SIZE):
            conn.execute(_UPSERT_ACTUALS, batch)
    return len(params)


def upsert_forecasts(engine: Engine, points: Sequence[ForecastPoint]) -> int:
    """Insert or update forecasts, keeping every row as received."""
    params = [
        {
            "start_time": p.start_time,
            "publish_time": p.publish_time,
            "generation_mw": p.generation_mw,
        }
        for p in points
    ]
    with engine.begin() as conn:
        for batch in _batches(params, BATCH_SIZE):
            conn.execute(_UPSERT_FORECASTS, batch)
    return len(params)


def summary(engine: Engine) -> dict[str, dict[str, Any]]:
    """Row counts and time ranges, used to verify a load."""
    with engine.connect() as conn:
        actuals = (
            conn.execute(
                text(
                    "SELECT count(*) AS row_count, min(start_time) AS first_time, "
                    "max(start_time) AS last_time FROM wind_actuals"
                )
            )
            .mappings()
            .one()
        )
        forecasts = (
            conn.execute(
                text(
                    "SELECT count(*) AS row_count, "
                    "min(start_time) AS first_target, max(start_time) AS last_target, "
                    "min(publish_time) AS first_publish, max(publish_time) AS last_publish, "
                    "count(*) FILTER (WHERE publish_time > start_time) AS published_after_target "
                    "FROM wind_forecasts"
                )
            )
            .mappings()
            .one()
        )
    return {"actuals": dict(actuals), "forecasts": dict(forecasts)}


def _as_utc(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Make time columns timezone-aware UTC with one consistent dtype."""
    for column in columns:
        frame[column] = pd.to_datetime(frame[column], utc=True).astype("datetime64[ns, UTC]")
    return frame


def load_actuals(engine: Engine, start: datetime, end: datetime) -> pd.DataFrame:
    """Actuals with start_time in [start, end). Columns: start_time, generation_mw."""
    query = text(
        "SELECT start_time, generation_mw FROM wind_actuals "
        "WHERE start_time >= :start AND start_time < :end ORDER BY start_time"
    )
    with engine.connect() as conn:
        frame = pd.read_sql(query, conn, params={"start": start, "end": end})
    return _as_utc(frame, ("start_time",))


def load_forecasts(engine: Engine, start: datetime, end: datetime) -> pd.DataFrame:
    """Forecasts whose TARGET start_time is in [start, end), every publish time included.

    Columns: start_time, publish_time, generation_mw.
    """
    query = text(
        "SELECT start_time, publish_time, generation_mw FROM wind_forecasts "
        "WHERE start_time >= :start AND start_time < :end ORDER BY start_time, publish_time"
    )
    with engine.connect() as conn:
        frame = pd.read_sql(query, conn, params={"start": start, "end": end})
    return _as_utc(frame, ("start_time", "publish_time"))


def freshness(engine: Engine) -> tuple[datetime | None, datetime | None]:
    """Latest actual start_time and latest forecast publish_time in the database."""
    query = text(
        "SELECT (SELECT max(start_time) FROM wind_actuals) AS actuals_last, "
        "(SELECT max(publish_time) FROM wind_forecasts) AS forecasts_last"
    )
    with engine.connect() as conn:
        row = conn.execute(query).one()
    return row.actuals_last, row.forecasts_last
