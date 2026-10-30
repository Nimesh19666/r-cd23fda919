"""DataSource backed by the Postgres database."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.repositories import wind


class DatabaseSource:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def load_forecasts(self, start: datetime, end: datetime) -> pd.DataFrame:
        return wind.load_forecasts(self._engine, start, end)

    def load_actuals(self, start: datetime, end: datetime) -> pd.DataFrame:
        return wind.load_actuals(self._engine, start, end)

    def freshness(self) -> tuple[datetime | None, datetime | None]:
        return wind.freshness(self._engine)

    def ping(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return False
        return True
