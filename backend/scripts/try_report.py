"""Try the report end to end against the real database. Usage (from backend/, venv active):

python scripts/try_report.py [delivery-date]      # default 2026-01-15
"""

import sys
from datetime import date, timedelta

from app.core.config import get_settings
from app.db import get_engine
from app.repositories import wind
from app.services.forecast_selection import delivery_window
from app.services.reports import build_accuracy_report, build_decision_view


def main() -> None:
    settings = get_settings()
    tz, cutoff = settings.tz, settings.decision_cutoff_local
    delivery = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 1, 15)

    # Decisions made 1-31 Jan are for delivery days 2 Jan - 1 Feb.
    first = settings.decision_start_date + timedelta(days=1)
    last = settings.decision_end_date + timedelta(days=1)
    start, _ = delivery_window(first, tz)
    _, end = delivery_window(last, tz)

    engine = get_engine()
    forecasts = wind.load_forecasts(engine, start, end)
    actuals = wind.load_actuals(engine, start, end)
    print(f"Loaded {len(forecasts)} forecasts and {len(actuals)} actuals for {first} to {last}")

    view = build_decision_view(forecasts, actuals, delivery, cutoff, tz)
    print(f"\n=== Decision view: delivery {delivery}, cutoff {view.cutoff_utc} ===")
    print(view.selected.head(6).to_string())
    print("...")
    print(view.summary)

    report = build_accuracy_report(forecasts, actuals, first, last, cutoff, tz)
    print(f"\n=== Accuracy report: delivery {first} to {last} ===")
    print(report.summary)
    columns = ["group", "n_compared", "mae_mw", "bias_mw", "p90_abs_error_mw"]
    print("\nBy hour of day:\n", report.by_hour[columns].round(1).to_string(index=False))
    print("\nBy forecast horizon:\n", report.by_horizon[columns].round(1).to_string(index=False))
    excluded = report.n_published_after_target
    print("\nForecast rows published after their target (excluded):", excluded)


if __name__ == "__main__":
    main()
