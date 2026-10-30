"""Diagnose the systematic over-forecast seen in the accuracy report.

Usage (from backend/, venv active):   python scripts/diagnose_bias.py

Three checks:
  1. By wind level: is the error a constant offset (e.g. missing embedded wind) or
     proportional to output (a scaling problem)?
  2. Time alignment: does the error shrink if actuals are shifted? (If yes, our timestamps
     are misaligned; if the minimum is at 0 minutes, alignment is right.)
  3. Is the over-forecast present on (almost) every day, or driven by a few?
"""

from datetime import timedelta

import pandas as pd

from app.core.config import get_settings
from app.db import get_engine
from app.repositories import wind
from app.services.forecast_selection import delivery_window, select_forecasts
from app.services.metrics import compare


def main() -> None:
    settings = get_settings()
    tz, cutoff = settings.tz, settings.decision_cutoff_local
    first = settings.decision_start_date + timedelta(days=1)
    last = settings.decision_end_date + timedelta(days=1)
    start, _ = delivery_window(first, tz)
    _, end = delivery_window(last, tz)

    engine = get_engine()
    forecasts = wind.load_forecasts(engine, start, end)
    actuals = wind.load_actuals(engine, start, end)

    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    selected = pd.concat(
        [select_forecasts(forecasts, day, cutoff, tz) for day in days], ignore_index=True
    )
    comparison = compare(selected, actuals).dropna(subset=["error_mw"]).reset_index(drop=True)

    mean_forecast = comparison["forecast_mw"].mean()
    mean_actual = comparison["actual_mw"].mean()
    print(f"{len(comparison)} comparisons")
    print(
        f"mean forecast {mean_forecast:.0f} MW, mean actual {mean_actual:.0f} MW, "
        f"ratio {mean_forecast / mean_actual:.3f}"
    )

    print("\n1. Error by wind level (quintiles of actual output):")
    labels = ["lowest", "low", "middle", "high", "highest"]
    comparison["level"] = pd.qcut(comparison["actual_mw"], 5, labels=labels)
    table = comparison.groupby("level", observed=True).agg(
        mean_actual=("actual_mw", "mean"),
        mean_forecast=("forecast_mw", "mean"),
        mean_error=("error_mw", "mean"),
    )
    table["ratio"] = table["mean_forecast"] / table["mean_actual"]
    print(table.round(2).to_string())

    print("\n2. Time alignment (forecast at T compared with the actual at T + shift):")
    for minutes in (-120, -90, -60, -30, 0, 30, 60, 90, 120):
        shifted = actuals.assign(start_time=actuals["start_time"] - timedelta(minutes=minutes))
        result = compare(selected, shifted).dropna(subset=["error_mw"])
        print(
            f"   shift {minutes:+4d} min: n={len(result):4d}  "
            f"MAE={result['abs_error_mw'].mean():7.0f}  bias={result['error_mw'].mean():+7.0f}"
        )

    print("\n3. Consistency across days:")
    local_day = comparison["start_time"].dt.tz_convert(tz).dt.date
    daily = comparison.groupby(local_day)["error_mw"].mean()
    print(f"   days with average over-forecast: {(daily > 0).sum()} of {len(daily)}")
    print(
        f"   smallest / median / largest daily bias: "
        f"{daily.min():+.0f} / {daily.median():+.0f} / {daily.max():+.0f} MW"
    )


if __name__ == "__main__":
    main()
