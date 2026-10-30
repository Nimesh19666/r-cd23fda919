"""Tests for forecast error metrics, checked against hand calculations."""

import pandas as pd
import pytest
from pandas.errors import MergeError

from app.services.metrics import compare, summarise_by_group, summarise_errors

T = ["2026-01-05T00:00Z", "2026-01-05T01:00Z", "2026-01-05T02:00Z", "2026-01-05T03:00Z"]
PUBLISHED = "2026-01-04T08:00Z"


def forecasts_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """(start_time, publish_time, generation_mw) tuples -> forecast table."""
    return pd.DataFrame(
        {
            "start_time": pd.to_datetime([r[0] for r in rows], utc=True),
            "publish_time": pd.to_datetime([r[1] for r in rows], utc=True),
            "generation_mw": pd.Series([r[2] for r in rows], dtype="float64"),
        }
    )


def actuals_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    """(start_time, generation_mw) tuples -> actuals table."""
    return pd.DataFrame(
        {
            "start_time": pd.to_datetime([r[0] for r in rows], utc=True),
            "generation_mw": pd.Series([r[1] for r in rows], dtype="float64"),
        }
    )


def example_comparison() -> pd.DataFrame:
    """Forecasts 100/200/300/400 vs actuals 90/210/330/400 -> errors +10/-10/-30/0."""
    forecasts = forecasts_frame([(T[i], PUBLISHED, f) for i, f in enumerate([100, 200, 300, 400])])
    actuals = actuals_frame([(T[i], a) for i, a in enumerate([90, 210, 330, 400])])
    return compare(forecasts, actuals)


def test_error_is_forecast_minus_actual() -> None:
    result = compare(forecasts_frame([(T[0], PUBLISHED, 100.0)]), actuals_frame([(T[0], 90.0)]))
    assert result.loc[0, "error_mw"] == 10.0  # over-forecast is positive
    assert result.loc[0, "abs_error_mw"] == 10.0


def test_under_forecast_is_negative() -> None:
    result = compare(forecasts_frame([(T[0], PUBLISHED, 90.0)]), actuals_frame([(T[0], 100.0)]))
    assert result.loc[0, "error_mw"] == -10.0


def test_horizon_hours_is_target_minus_publish_time() -> None:
    result = compare(forecasts_frame([(T[0], PUBLISHED, 1.0)]), actuals_frame([(T[0], 1.0)]))
    assert result.loc[0, "horizon_hours"] == 16.0


def test_missing_actual_stays_missing_and_is_not_zero() -> None:
    result = compare(forecasts_frame([(T[0], PUBLISHED, 100.0)]), actuals_frame([]))
    assert len(result) == 1  # the forecast row is kept
    assert pd.isna(result.loc[0, "actual_mw"])
    assert pd.isna(result.loc[0, "error_mw"])


def test_duplicate_actuals_are_rejected() -> None:
    actuals = actuals_frame([(T[0], 90.0), (T[0], 95.0)])
    with pytest.raises(MergeError):
        compare(forecasts_frame([(T[0], PUBLISHED, 100.0)]), actuals)


def test_summary_matches_hand_calculation() -> None:
    summary = summarise_errors(example_comparison())
    assert summary.n_forecasts == 4
    assert summary.n_compared == 4
    assert summary.n_missing_actual == 0
    assert summary.mae_mw == pytest.approx(12.5)  # (10 + 10 + 30 + 0) / 4
    assert summary.rmse_mw == pytest.approx(275**0.5)  # sqrt((100 + 100 + 900 + 0) / 4)
    assert summary.bias_mw == pytest.approx(-7.5)  # (10 - 10 - 30 + 0) / 4
    assert summary.p50_abs_error_mw == pytest.approx(10.0)  # sorted abs errors 0, 10, 10, 30
    assert summary.p90_abs_error_mw == pytest.approx(24.0)  # 10 + 0.7 * (30 - 10)
    assert summary.p95_abs_error_mw == pytest.approx(27.0)  # 10 + 0.85 * (30 - 10)
    assert summary.mean_actual_mw == pytest.approx(257.5)  # 1030 / 4
    assert summary.mae_pct_of_mean_actual == pytest.approx(12.5 / 257.5 * 100)


def test_missing_actuals_are_counted_and_excluded() -> None:
    forecasts = forecasts_frame([(T[i], PUBLISHED, f) for i, f in enumerate([100, 200, 300])])
    actuals = actuals_frame([(T[0], 90.0), (T[1], 210.0)])  # nothing for T[2]
    summary = summarise_errors(compare(forecasts, actuals))
    assert summary.n_forecasts == 3
    assert summary.n_compared == 2
    assert summary.n_missing_actual == 1
    assert summary.mae_mw == pytest.approx(10.0)  # only the two real errors: +10 and -10
    assert summary.bias_mw == pytest.approx(0.0)


def test_nothing_to_compare_gives_none_not_a_crash_or_zero() -> None:
    summary = summarise_errors(compare(forecasts_frame([]), actuals_frame([])))
    assert summary.n_forecasts == 0
    assert summary.n_compared == 0
    assert summary.mae_mw is None
    assert summary.p95_abs_error_mw is None


def test_percentage_is_none_when_mean_actual_is_zero() -> None:
    comparison = compare(forecasts_frame([(T[0], PUBLISHED, 10.0)]), actuals_frame([(T[0], 0.0)]))
    summary = summarise_errors(comparison)
    assert summary.mae_mw == pytest.approx(10.0)
    assert summary.mae_pct_of_mean_actual is None  # no division by zero


def test_summarise_by_group_runs_each_group_separately() -> None:
    comparison = example_comparison()  # errors +10, -10, -30, 0
    groups = pd.Series(["a", "a", "b", "b"], index=comparison.index)
    result = summarise_by_group(comparison, groups)
    assert result["group"].tolist() == ["a", "b"]
    assert result["mae_mw"].tolist() == [10.0, 15.0]  # (10+10)/2 and (30+0)/2


def test_naive_timestamps_are_rejected() -> None:
    forecasts = pd.DataFrame(
        {
            "start_time": pd.to_datetime(["2026-01-05T00:00"]),
            "publish_time": pd.to_datetime(["2026-01-04T08:00"]),
            "generation_mw": [1.0],
        }
    )
    with pytest.raises(ValueError, match="timezone"):
        compare(forecasts, actuals_frame([(T[0], 1.0)]))


def test_missing_columns_are_rejected() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        compare(pd.DataFrame({"start_time": []}), actuals_frame([]))


def test_signed_error_percentiles_show_direction() -> None:
    summary = summarise_errors(example_comparison())  # errors +10, -10, -30, 0
    assert summary.p10_error_mw == pytest.approx(-24.0)  # sorted -30, -10, 0, 10: -30 + 0.3 * 20
    assert summary.p50_error_mw == pytest.approx(-5.0)  # halfway between -10 and 0
    assert summary.p90_error_mw == pytest.approx(7.0)  # 0 + 0.7 * 10


def test_signed_error_percentiles_are_none_when_nothing_compared() -> None:
    summary = summarise_errors(compare(forecasts_frame([]), actuals_frame([])))
    assert summary.p10_error_mw is None
    assert summary.p90_error_mw is None
