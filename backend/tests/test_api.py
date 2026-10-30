"""API tests: real routes and service, fake in-memory data."""

from datetime import date, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.report_service import MarketConfig, ReportService
from tests.fakes import (
    FailingSource,
    InMemorySource,
    actuals_frame,
    two_day_actuals,
    two_day_forecasts,
)

# Decisions on 4-5 Jan mean delivery days 5-6 Jan.
CONFIG = MarketConfig(
    cutoff_local=time(9, 0),
    tz=ZoneInfo("Europe/London"),
    decision_start_date=date(2026, 1, 4),
    decision_end_date=date(2026, 1, 5),
)


def make_client(source: object) -> TestClient:
    return TestClient(create_app(ReportService(source, CONFIG)))  # type: ignore[arg-type]


def normal_source() -> InMemorySource:
    return InMemorySource(two_day_forecasts(), two_day_actuals())


def test_health_ok() -> None:
    response = make_client(normal_source()).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database_ok": True}


def test_health_reports_degraded_instead_of_failing() -> None:
    response = make_client(FailingSource()).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database_ok": False}


def test_meta_describes_the_assumptions() -> None:
    body = make_client(normal_source()).get("/api/meta").json()
    assert body["cutoff_local"] == "09:00"
    assert body["timezone"] == "Europe/London"
    assert body["first_delivery_date"] == "2026-01-05"
    assert body["last_delivery_date"] == "2026-01-06"
    assert "forecast - actual" in body["error_definition"]
    assert len(body["notes"]) > 0
    assert body["forecasts_last_publish_time"] is not None


def test_decision_returns_the_forecast_known_at_the_cutoff() -> None:
    response = make_client(normal_source()).get("/api/decision?delivery_date=2026-01-05")
    assert response.status_code == 200
    body = response.json()
    assert body["cutoff_utc"] == "2026-01-04T09:00:00Z"
    assert [p["forecast_mw"] for p in body["points"]] == [120.0, 200.0]  # never the 999 MW one
    first = body["points"][0]
    assert first["publish_time"] == "2026-01-04T08:00:00Z"
    assert first["horizon_hours"] == 16.0
    assert first["actual_mw"] == 110.0
    assert first["error_mw"] == 10.0
    assert len(body["actuals"]) == 3  # the three half-hours of 5 Jan only
    assert body["summary"]["mae_mw"] == pytest.approx(10.0)


def test_decision_includes_a_direction_aware_range_from_the_backtest() -> None:
    body = make_client(normal_source()).get("/api/decision?delivery_date=2026-01-05").json()
    first, second = body["points"]
    # Backtest signed errors sorted: -30, 0, 10, 10 -> P10 = -21, P90 = 10.
    assert first["range_low_mw"] == pytest.approx(110.0)  # 120 - 10
    assert first["range_high_mw"] == pytest.approx(141.0)  # 120 + 21
    assert second["range_low_mw"] == pytest.approx(190.0)
    assert second["range_high_mw"] == pytest.approx(221.0)
    assert "backtest" in body["range_note"]


def test_missing_actual_is_null_not_nan() -> None:
    actuals = actuals_frame(
        [("2026-01-05T00:00Z", 110.0), ("2026-01-06T00:00Z", 330.0), ("2026-01-06T01:00Z", 400.0)]
    )
    client = make_client(InMemorySource(two_day_forecasts(), actuals))
    response = client.get("/api/decision?delivery_date=2026-01-05")
    assert response.status_code == 200  # NaN in the JSON would have made this a 500
    second = response.json()["points"][1]
    assert second["actual_mw"] is None
    assert second["error_mw"] is None


def test_date_outside_the_scope_is_rejected_with_a_clear_message() -> None:
    response = make_client(normal_source()).get("/api/decision?delivery_date=2026-02-15")
    assert response.status_code == 422
    assert "between 2026-01-05 and 2026-01-06" in response.json()["detail"]


@pytest.mark.parametrize("query", ["", "?delivery_date=not-a-date"])
def test_missing_or_malformed_date_is_rejected(query: str) -> None:
    response = make_client(normal_source()).get(f"/api/decision{query}")
    assert response.status_code == 422


def test_accuracy_returns_summary_and_breakdowns() -> None:
    body = make_client(normal_source()).get("/api/accuracy").json()
    assert body["cutoff_local"] == "09:00"
    assert body["summary"]["n_compared"] == 4
    assert body["summary"]["mae_mw"] == pytest.approx(12.5)
    assert body["summary"]["bias_mw"] == pytest.approx(-2.5)
    assert [g["label"] for g in body["by_day"]] == ["2026-01-05", "2026-01-06"]
    assert [g["label"] for g in body["by_hour"]] == ["00", "01"]
    assert body["n_published_after_target"] == 0


def test_accuracy_report_is_computed_once_and_cached() -> None:
    source = normal_source()
    client = make_client(source)
    client.get("/api/accuracy")
    client.get("/api/accuracy")
    assert source.forecast_loads == 1


def test_database_failure_gives_503_without_leaking_details() -> None:
    response = make_client(FailingSource()).get("/api/accuracy")
    assert response.status_code == 503
    assert response.json() == {"detail": "The database is currently unavailable."}
    assert "secret" not in response.text


def test_openapi_lists_every_endpoint() -> None:
    paths = make_client(normal_source()).get("/openapi.json").json()["paths"]
    for path in ("/api/health", "/api/meta", "/api/decision", "/api/accuracy"):
        assert path in paths
