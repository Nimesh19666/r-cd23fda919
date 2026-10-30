"""Response models for the HTTP API: the exact JSON the frontend receives.

Sign convention everywhere:  error = forecast - actual
    error > 0  the forecast was too high (over-forecast)
    error < 0  the forecast was too low (under-forecast)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ErrorSummaryOut(BaseModel):
    """Accuracy numbers for a set of forecasts. Metrics are null when nothing was compared."""

    n_forecasts: int = Field(description="Forecasts considered")
    n_compared: int = Field(description="Forecasts that had an actual to compare against")
    n_missing_actual: int = Field(description="Forecasts with no actual (left out of metrics)")
    mae_mw: float | None = Field(description="Mean absolute error, MW")
    rmse_mw: float | None = Field(description="Root mean squared error, MW")
    bias_mw: float | None = Field(description="Mean signed error, MW. Positive = over-forecast")
    p10_error_mw: float | None = Field(description="10th percentile of signed error, MW")
    p50_error_mw: float | None = Field(description="Median signed error, MW")
    p90_error_mw: float | None = Field(description="90th percentile of signed error, MW")
    p50_abs_error_mw: float | None = Field(description="Median absolute error, MW")
    p90_abs_error_mw: float | None = Field(description="90th percentile absolute error, MW")
    p95_abs_error_mw: float | None = Field(description="95th percentile absolute error, MW")
    mean_actual_mw: float | None = Field(description="Average actual wind generation, MW")
    mae_pct_of_mean_actual: float | None = Field(description="MAE as % of mean actual wind")


class GroupSummaryOut(ErrorSummaryOut):
    """Accuracy for one group: a delivery day, an hour of day or a forecast-horizon bucket."""

    label: str = Field(description="Group label, e.g. '2026-01-15', '07' or '12-18h'")


class DecisionPoint(BaseModel):
    """The forecast the buyer could see for one target time, plus what happened afterwards."""

    start_time: datetime
    publish_time: datetime = Field(description="When the forecast used here was published")
    horizon_hours: float = Field(description="Hours between publish_time and start_time")
    forecast_mw: float
    actual_mw: float | None = Field(description="Known only after the delivery day")
    error_mw: float | None = Field(description="forecast_mw - actual_mw")
    range_low_mw: float | None = Field(
        default=None, description="Typical low end for actual wind (see range_note)"
    )
    range_high_mw: float | None = Field(
        default=None, description="Typical high end for actual wind (see range_note)"
    )


class ActualPointOut(BaseModel):
    start_time: datetime
    actual_mw: float


class DecisionResponse(BaseModel):
    delivery_date: date
    cutoff_utc: datetime = Field(description="Decision cutoff: forecasts after this are unseen")
    points: list[DecisionPoint]
    actuals: list[ActualPointOut] = Field(
        description=(
            "Half-hourly actuals for the day. A retrospective overlay, not known at decision time."
        )
    )
    summary: ErrorSummaryOut = Field(description="Accuracy of this day's decision-time forecast")
    range_note: str | None = Field(default=None, description="How range_low/high were derived")


class AccuracyResponse(BaseModel):
    first_delivery_date: date
    last_delivery_date: date
    cutoff_local: str
    timezone: str
    summary: ErrorSummaryOut
    by_day: list[GroupSummaryOut]
    by_hour: list[GroupSummaryOut]
    by_horizon: list[GroupSummaryOut] = Field(
        description="Every forecast published before its target time, grouped by forecast age"
    )
    n_published_after_target: int = Field(
        description="Forecast rows published after their target time (excluded from by_horizon)"
    )


class MetaResponse(BaseModel):
    cutoff_local: str
    timezone: str
    decision_start_date: date
    decision_end_date: date
    first_delivery_date: date
    last_delivery_date: date
    error_definition: str
    notes: list[str]
    actuals_last_time: datetime | None
    forecasts_last_publish_time: datetime | None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database_ok: bool
