"""In-memory stand-ins for the database, used by API tests."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy.exc import OperationalError


def forecasts_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "start_time": pd.to_datetime([r[0] for r in rows], utc=True),
            "publish_time": pd.to_datetime([r[1] for r in rows], utc=True),
            "generation_mw": pd.Series([r[2] for r in rows], dtype="float64"),
        }
    )


def actuals_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "start_time": pd.to_datetime([r[0] for r in rows], utc=True),
            "generation_mw": pd.Series([r[1] for r in rows], dtype="float64"),
        }
    )


def two_day_forecasts() -> pd.DataFrame:
    return forecasts_frame(
        [
            ("2026-01-05T00:00Z", "2026-01-04T06:00Z", 100.0),
            ("2026-01-05T00:00Z", "2026-01-04T08:00Z", 120.0),  # latest before the cutoff
            ("2026-01-05T00:00Z", "2026-01-04T12:00Z", 999.0),  # after the cutoff: ignored
            ("2026-01-05T01:00Z", "2026-01-04T08:00Z", 200.0),
            ("2026-01-06T00:00Z", "2026-01-05T08:00Z", 300.0),
            ("2026-01-06T01:00Z", "2026-01-05T08:00Z", 400.0),
        ]
    )


def two_day_actuals() -> pd.DataFrame:
    return actuals_frame(
        [
            ("2026-01-05T00:00Z", 110.0),
            ("2026-01-05T01:00Z", 190.0),
            ("2026-01-05T02:00Z", 500.0),
            ("2026-01-06T00:00Z", 330.0),
            ("2026-01-06T01:00Z", 400.0),
        ]
    )


class InMemorySource:
    def __init__(
        self, forecasts: pd.DataFrame, actuals: pd.DataFrame, healthy: bool = True
    ) -> None:
        self._forecasts = forecasts
        self._actuals = actuals
        self._healthy = healthy
        self.forecast_loads = 0

    def load_forecasts(self, start: datetime, end: datetime) -> pd.DataFrame:
        self.forecast_loads += 1
        f = self._forecasts
        return f[(f["start_time"] >= start) & (f["start_time"] < end)].reset_index(drop=True)

    def load_actuals(self, start: datetime, end: datetime) -> pd.DataFrame:
        a = self._actuals
        return a[(a["start_time"] >= start) & (a["start_time"] < end)].reset_index(drop=True)

    def freshness(self) -> tuple[datetime | None, datetime | None]:
        return self._actuals["start_time"].max(), self._forecasts["publish_time"].max()

    def ping(self) -> bool:
        return self._healthy


class FailingSource:
    """A database that is down. The error text contains a fake secret on purpose."""

    def _fail(self) -> None:
        raise OperationalError("SELECT 1", {}, Exception("password=secret"))

    def load_forecasts(self, start: datetime, end: datetime) -> pd.DataFrame:
        self._fail()
        raise AssertionError("unreachable")

    def load_actuals(self, start: datetime, end: datetime) -> pd.DataFrame:
        self._fail()
        raise AssertionError("unreachable")

    def freshness(self) -> tuple[datetime | None, datetime | None]:
        self._fail()
        raise AssertionError("unreachable")

    def ping(self) -> bool:
        return False
