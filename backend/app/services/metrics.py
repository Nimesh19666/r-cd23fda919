"""Forecast error measurement. Pure functions: data in, numbers out.

Sign convention, used everywhere:   error = forecast - actual
    error > 0  over-forecast   (forecast too high: the buyer would buy too little other power)
    error < 0  under-forecast  (forecast too low: the buyer would buy too much other power)

Forecasts are joined to actuals on exact start_time. A forecast with no actual is kept in the
table with a missing actual and is COUNTED, never treated as zero and never silently dropped.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd

FORECAST_COLUMNS = ("start_time", "publish_time", "generation_mw")
ACTUAL_COLUMNS = ("start_time", "generation_mw")
TIME_COLUMNS = ("start_time", "publish_time")


@dataclass(frozen=True)
class ErrorSummary:
    """Accuracy numbers for a set of forecasts. Metrics are None when nothing was compared."""

    n_forecasts: int  # forecasts considered
    n_compared: int  # forecasts that had an actual to compare against
    n_missing_actual: int  # forecasts with no actual (excluded from the metrics below)
    mae_mw: float | None  # mean absolute error
    rmse_mw: float | None  # root mean squared error (punishes large misses)
    bias_mw: float | None  # mean signed error: >0 over-forecasts on average
    p10_error_mw: float | None  # signed error: 10% of errors are below this
    p50_error_mw: float | None  # median signed error
    p90_error_mw: float | None  # signed error: 90% of errors are below this
    # So 80% of the time the actual was between forecast - p90 and forecast - p10.
    p50_abs_error_mw: float | None  # median absolute error
    p90_abs_error_mw: float | None  # 90% of errors are no bigger than this
    p95_abs_error_mw: float | None
    mean_actual_mw: float | None
    mae_pct_of_mean_actual: float | None  # MAE relative to average wind (not MAPE)


def _require(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")
    for column in columns:
        if column in TIME_COLUMNS and not isinstance(frame[column].dtype, pd.DatetimeTZDtype):
            raise ValueError(f"{name}.{column} must be timezone-aware datetimes")


def compare(forecasts: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Join forecasts to actuals and compute the error of each forecast.

    forecasts: start_time, publish_time, generation_mw (many forecasts per start_time is fine)
    actuals:   start_time, generation_mw (must be unique per start_time, else an error is raised)
    Output columns: start_time, publish_time, forecast_mw, actual_mw, horizon_hours,
    error_mw, abs_error_mw. One row per input forecast.
    """
    _require(forecasts, FORECAST_COLUMNS, "forecasts")
    _require(actuals, ACTUAL_COLUMNS, "actuals")

    left = forecasts[list(FORECAST_COLUMNS)].rename(columns={"generation_mw": "forecast_mw"})
    right = actuals[list(ACTUAL_COLUMNS)].rename(columns={"generation_mw": "actual_mw"})
    # many_to_one: duplicate actuals would silently multiply rows, so pandas must refuse.
    merged = left.merge(right, on="start_time", how="left", validate="many_to_one")

    merged["horizon_hours"] = (
        merged["start_time"] - merged["publish_time"]
    ).dt.total_seconds() / 3600
    merged["error_mw"] = merged["forecast_mw"] - merged["actual_mw"]
    merged["abs_error_mw"] = merged["error_mw"].abs()
    return merged


def summarise_errors(comparison: pd.DataFrame) -> ErrorSummary:
    """Accuracy metrics for the output of compare(). Rows without an actual are counted only."""
    n_forecasts = len(comparison)
    valid = comparison[comparison["error_mw"].notna()]
    n_compared = len(valid)
    counts = {
        "n_forecasts": n_forecasts,
        "n_compared": n_compared,
        "n_missing_actual": n_forecasts - n_compared,
    }
    if n_compared == 0:
        return ErrorSummary(
            **counts,
            mae_mw=None,
            rmse_mw=None,
            bias_mw=None,
            p10_error_mw=None,
            p50_error_mw=None,
            p90_error_mw=None,
            p50_abs_error_mw=None,
            p90_abs_error_mw=None,
            p95_abs_error_mw=None,
            mean_actual_mw=None,
            mae_pct_of_mean_actual=None,
        )

    errors = valid["error_mw"]
    abs_errors = valid["abs_error_mw"]
    percentiles = abs_errors.quantile([0.5, 0.9, 0.95])  # linear interpolation
    signed = errors.quantile([0.1, 0.5, 0.9])
    mae = float(abs_errors.mean())
    mean_actual = float(valid["actual_mw"].mean())
    return ErrorSummary(
        **counts,
        mae_mw=mae,
        rmse_mw=math.sqrt(float((errors**2).mean())),
        bias_mw=float(errors.mean()),
        p10_error_mw=float(signed.loc[0.1]),
        p50_error_mw=float(signed.loc[0.5]),
        p90_error_mw=float(signed.loc[0.9]),
        p50_abs_error_mw=float(percentiles.loc[0.5]),
        p90_abs_error_mw=float(percentiles.loc[0.9]),
        p95_abs_error_mw=float(percentiles.loc[0.95]),
        mean_actual_mw=mean_actual,
        mae_pct_of_mean_actual=mae / mean_actual * 100 if mean_actual > 0 else None,
    )


def summarise_by_group(comparison: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """Run summarise_errors separately per group (e.g. hour of day or horizon bucket).

    groups: one label per row of comparison, with the same index.
    Output: one row per group label, sorted by label, with a 'group' column plus all metrics.
    """
    rows = []
    for label, part in comparison.groupby(groups, observed=True, sort=True):
        rows.append({"group": label, **asdict(summarise_errors(part))})
    return pd.DataFrame(rows)
