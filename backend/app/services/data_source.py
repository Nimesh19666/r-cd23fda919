"""The interface the report service needs from a data store."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd


class DataSource(Protocol):
    def load_forecasts(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Forecasts whose target start_time is in [start, end)."""
        ...

    def load_actuals(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Actuals with start_time in [start, end)."""
        ...

    def freshness(self) -> tuple[datetime | None, datetime | None]:
        """(latest actual start_time, latest forecast publish_time)."""
        ...

    def ping(self) -> bool:
        """True if the store is reachable. Must never raise."""
        ...
