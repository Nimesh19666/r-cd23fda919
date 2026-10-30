"""Elexon BMRS client: wind actuals (FUELHH) and wind forecasts (WINDFOR).

This module only talks HTTP and validates what comes back. It knows nothing about the
database or the forecast-selection rules. Requests are made one day at a time so no single
call can hit a range limit or be silently truncated.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from types import TracebackType
from typing import Any, Literal, TypeVar

import httpx
from pydantic import AwareDatetime, BaseModel, ValidationError

from app.core.config import get_settings
from app.domain.models import ActualPoint, ForecastPoint

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0
RETRY_STATUS = {429, 500, 502, 503, 504}

ModelT = TypeVar("ModelT", bound=BaseModel)


class ElexonError(RuntimeError):
    """Raised when Elexon cannot be reached or returns data we do not accept."""


class _ActualRecord(BaseModel):
    """One FUELHH row. Field names match the API; extra fields are ignored."""

    startTime: AwareDatetime
    publishTime: AwareDatetime
    fuelType: Literal["WIND"]
    generation: float


class _ForecastRecord(BaseModel):
    """One WINDFOR row."""

    startTime: AwareDatetime
    publishTime: AwareDatetime
    generation: float


def _validate(model: type[ModelT], raw: dict[str, Any], dataset: str) -> ModelT:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ElexonError(f"{dataset}: unexpected record {raw!r}: {exc}") from exc


def _days(first_day: date, last_day: date) -> Iterator[date]:
    current = first_day
    while current <= last_day:
        yield current
        current += timedelta(days=1)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


class ElexonClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        base_url: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = (base_url or get_settings().elexon_base_url).rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=60, headers={"Accept": "application/json"})
        self._sleep = sleep  # injectable so tests do not really wait

    def __enter__(self) -> ElexonClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get_rows(self, dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
        """GET one stream request, retrying temporary failures with backoff."""
        url = f"{self._base_url}/datasets/{dataset}/stream"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._client.get(url, params=params)
            except httpx.TransportError as exc:
                problem = f"network error {exc!r}"
            else:
                if response.status_code == 200:
                    payload = response.json()
                    rows = payload.get("data") if isinstance(payload, dict) else payload
                    if not isinstance(rows, list):
                        raise ElexonError(f"{dataset} {params}: response is not a list")
                    return rows
                problem = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUS:
                    raise ElexonError(f"{dataset} {params}: {problem}: {response.text[:300]}")
            if attempt == MAX_ATTEMPTS:
                raise ElexonError(
                    f"{dataset} {params}: gave up after {attempt} attempts ({problem})"
                )
            delay = BACKOFF_SECONDS * 2 ** (attempt - 1)
            logger.warning("%s %s: %s, retrying in %.0fs", dataset, params, problem, delay)
            self._sleep(delay)
        raise AssertionError("unreachable")

    def fetch_actuals(self, first_day: date, last_day: date) -> list[ActualPoint]:
        """Wind actuals for settlement days first_day..last_day inclusive, sorted by time.

        If Elexon returns more than one row for a half-hour, the latest publishTime wins.
        """
        latest: dict[datetime, tuple[datetime, float]] = {}
        for day in _days(first_day, last_day):
            params = {
                "settlementDateFrom": day.isoformat(),
                "settlementDateTo": day.isoformat(),
                "fuelType": "WIND",
            }
            rows = self._get_rows("FUELHH", params)
            logger.info("FUELHH %s: %d rows", day, len(rows))
            for raw in rows:
                record = _validate(_ActualRecord, raw, "FUELHH")
                previous = latest.get(record.startTime)
                if previous is None or record.publishTime > previous[0]:
                    latest[record.startTime] = (record.publishTime, record.generation)
        return [
            ActualPoint(start_time=start, generation_mw=generation)
            for start, (_, generation) in sorted(latest.items())
        ]

    def fetch_forecasts(self, first_day: date, last_day: date) -> list[ForecastPoint]:
        """Wind forecasts published between 00:00 UTC on first_day and the end of last_day.

        Every row is kept as received, including forecasts published after their target
        time; filtering happens later in the calculation layer. Rows that appear in two
        neighbouring daily requests are de-duplicated on (start_time, publish_time).
        """
        found: dict[tuple[datetime, datetime], float] = {}
        for day in _days(first_day, last_day):
            window_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
            params = {
                "publishDateTimeFrom": _iso(window_start),
                "publishDateTimeTo": _iso(window_start + timedelta(days=1)),
            }
            rows = self._get_rows("WINDFOR", params)
            logger.info("WINDFOR published %s: %d rows", day, len(rows))
            for raw in rows:
                record = _validate(_ForecastRecord, raw, "WINDFOR")
                found[(record.startTime, record.publishTime)] = record.generation
        return [
            ForecastPoint(start_time=start, publish_time=publish, generation_mw=generation)
            for (start, publish), generation in sorted(found.items())
        ]
