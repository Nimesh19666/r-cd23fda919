"""Tests for the decision view and accuracy report, using small handmade data."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.services.reports import build_accuracy_report, build_decision_view

LONDON = ZoneInfo("Europe/London")
CUTOFF = time(9, 0)
DAY = date(2026, 1, 5)


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
            ("2026-01-05T00:00Z", 110.0),  # error of the 120 forecast: +10
            ("2026-01-05T01:00Z", 190.0),  # error of the 200 forecast: +10
            ("2026-01-05T02:00Z", 500.0),  # no forecast for this hour
            ("2026-01-06T00:00Z", 330.0),  # error of the 300 forecast: -30
            ("2026-01-06T01:00Z", 400.0),  # error of the 400 forecast: 0
        ]
    )


def test_decision_view_shows_only_what_was_known_at_the_cutoff() -> None:
    view = build_decision_view(two_day_forecasts(), two_day_actuals(), DAY, CUTOFF, LONDON)
    assert view.cutoff_utc == datetime(2026, 1, 4, 9, 0, tzinfo=UTC)
    assert view.selected["generation_mw"].tolist() == [120.0, 200.0]  # not the 999 MW one


def test_decision_view_compares_against_that_days_actuals() -> None:
    view = build_decision_view(two_day_forecasts(), two_day_actuals(), DAY, CUTOFF, LONDON)
    assert len(view.actuals) == 3  # the three actuals of 5 Jan, not the 6 Jan ones
    assert view.summary.n_compared == 2
    assert view.summary.mae_mw == pytest.approx(10.0)
    assert view.summary.bias_mw == pytest.approx(10.0)  # over-forecast on average


def test_decision_view_counts_hours_without_an_actual() -> None:
    actuals = actuals_frame([("2026-01-05T00:00Z", 110.0)])
    view = build_decision_view(two_day_forecasts(), actuals, DAY, CUTOFF, LONDON)
    assert view.summary.n_forecasts == 2
    assert view.summary.n_missing_actual == 1


def test_accuracy_report_overall_summary() -> None:
    report = build_accuracy_report(
        two_day_forecasts(), two_day_actuals(), DAY, date(2026, 1, 6), CUTOFF, LONDON
    )
    assert report.summary.n_compared == 4
    assert report.summary.mae_mw == pytest.approx(12.5)  # errors +10, +10, -30, 0
    assert report.summary.bias_mw == pytest.approx(-2.5)


def test_accuracy_report_by_day() -> None:
    report = build_accuracy_report(
        two_day_forecasts(), two_day_actuals(), DAY, date(2026, 1, 6), CUTOFF, LONDON
    )
    assert report.by_day["group"].tolist() == [date(2026, 1, 5), date(2026, 1, 6)]
    assert report.by_day["mae_mw"].tolist() == [10.0, 15.0]  # (10+10)/2 and (30+0)/2


def test_accuracy_report_by_hour() -> None:
    report = build_accuracy_report(
        two_day_forecasts(), two_day_actuals(), DAY, date(2026, 1, 6), CUTOFF, LONDON
    )
    assert report.by_hour["group"].tolist() == [0, 1]
    assert report.by_hour["mae_mw"].tolist() == [20.0, 5.0]  # (10+30)/2 and (10+0)/2


def test_horizon_analysis_uses_every_forecast_published_before_its_target() -> None:
    target = "2026-01-05T00:00Z"
    forecasts = forecasts_frame(
        [
            (target, "2026-01-04T20:00Z", 110.0),  # 4 hours ahead
            (target, "2026-01-04T08:00Z", 90.0),  # 16 hours ahead
            (target, "2026-01-03T08:00Z", 130.0),  # 40 hours ahead
            (target, "2026-01-05T02:00Z", 777.0),  # published after the target: excluded
        ]
    )
    report = build_accuracy_report(
        forecasts, actuals_frame([(target, 100.0)]), DAY, DAY, CUTOFF, LONDON
    )
    assert report.by_horizon["group"].tolist() == ["0-6h", "12-18h", "36-48h"]
    assert report.by_horizon["mae_mw"].tolist() == [10.0, 10.0, 30.0]
    assert report.n_published_after_target == 1
    # The decision-time summary still uses only what was known at the cutoff (the 90 MW one).
    assert report.summary.n_compared == 1
    assert report.summary.bias_mw == pytest.approx(-10.0)


def test_no_data_gives_an_empty_report_without_crashing() -> None:
    report = build_accuracy_report(forecasts_frame([]), actuals_frame([]), DAY, DAY, CUTOFF, LONDON)
    assert report.summary.n_forecasts == 0
    assert report.summary.mae_mw is None
    assert report.by_day.empty
    assert report.by_hour.empty
    assert report.by_horizon.empty


def test_reversed_dates_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be after"):
        build_accuracy_report(
            forecasts_frame([]), actuals_frame([]), date(2026, 1, 6), DAY, CUTOFF, LONDON
        )
