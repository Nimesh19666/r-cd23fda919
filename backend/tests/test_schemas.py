"""Tests that the API schemas stay in step with the metrics code."""

from dataclasses import asdict, fields
from datetime import UTC, datetime

import pandas as pd

from app.schemas.api import DecisionPoint, ErrorSummaryOut, GroupSummaryOut
from app.services.metrics import ErrorSummary, summarise_errors


def test_schema_has_exactly_the_fields_of_the_metrics_dataclass() -> None:
    assert set(ErrorSummaryOut.model_fields) == {f.name for f in fields(ErrorSummary)}


def test_summary_converts_from_the_dataclass_including_none_metrics() -> None:
    empty = pd.DataFrame({"error_mw": [], "abs_error_mw": [], "actual_mw": []})
    summary = summarise_errors(empty)
    converted = ErrorSummaryOut.model_validate(asdict(summary))
    assert converted.n_compared == 0
    assert converted.mae_mw is None


def test_group_summary_adds_a_label_to_the_summary_fields() -> None:
    assert "label" in GroupSummaryOut.model_fields
    assert set(ErrorSummaryOut.model_fields) < set(GroupSummaryOut.model_fields)


def test_times_are_serialised_as_utc_iso_strings() -> None:
    point = DecisionPoint(
        start_time=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        publish_time=datetime(2026, 1, 4, 8, 0, tzinfo=UTC),
        horizon_hours=26.0,
        forecast_mw=100.0,
        actual_mw=None,
        error_mw=None,
    )
    assert '"start_time":"2026-01-05T10:00:00Z"' in point.model_dump_json()
