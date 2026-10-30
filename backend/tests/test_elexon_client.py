"""Elexon client tests. HTTP is mocked, and the sleep function is recorded, never waited on."""

from datetime import UTC, date, datetime

import httpx
import pytest

from app.clients.elexon import BACKOFF_SECONDS, MAX_ATTEMPTS, ElexonClient, ElexonError

BASE = "https://elexon.test/bmrs/api/v1"
DAY = date(2026, 1, 5)


class Script:
    """A fake Elexon. Replies with each step in turn, then repeats the last one forever."""

    def __init__(self, *steps: httpx.Response | Exception) -> None:
        self.steps = steps
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.steps[min(len(self.requests) - 1, len(self.steps) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


def make_client(script: Script) -> tuple[ElexonClient, list[float]]:
    sleeps: list[float] = []
    http = httpx.Client(transport=httpx.MockTransport(script))
    return ElexonClient(client=http, base_url=BASE, sleep=sleeps.append), sleeps


def ok(rows: object) -> httpx.Response:
    return httpx.Response(200, json=rows)


def actual_row(start: str, publish: str = "2026-01-05T00:00:00Z", mw: float = 1000.0) -> dict:
    return {"startTime": start, "publishTime": publish, "fuelType": "WIND", "generation": mw}


def forecast_row(start: str, publish: str, mw: float = 5000.0) -> dict:
    return {"startTime": start, "publishTime": publish, "generation": mw}


# ----- actuals -----


def test_actuals_are_returned_sorted_by_time() -> None:
    script = Script(ok([actual_row("2026-01-05T01:00:00Z"), actual_row("2026-01-05T00:00:00Z")]))
    client, _ = make_client(script)
    points = client.fetch_actuals(DAY, DAY)
    assert [p.start_time.hour for p in points] == [0, 1]


def test_actuals_ask_for_one_day_at_a_time_and_only_wind() -> None:
    script = Script(ok([]))
    client, _ = make_client(script)
    client.fetch_actuals(date(2026, 1, 5), date(2026, 1, 6))
    params = [dict(request.url.params) for request in script.requests]
    assert params == [
        {"settlementDateFrom": "2026-01-05", "settlementDateTo": "2026-01-05", "fuelType": "WIND"},
        {"settlementDateFrom": "2026-01-06", "settlementDateTo": "2026-01-06", "fuelType": "WIND"},
    ]
    assert script.requests[0].url.path.endswith("/datasets/FUELHH/stream")


def test_duplicate_half_hour_keeps_the_latest_publication() -> None:
    script = Script(
        ok(
            [
                actual_row("2026-01-05T00:00:00Z", publish="2026-01-05T10:00:00Z", mw=100),
                actual_row("2026-01-05T00:00:00Z", publish="2026-01-05T11:00:00Z", mw=200),
            ]
        )
    )
    client, _ = make_client(script)
    points = client.fetch_actuals(DAY, DAY)
    assert [p.generation_mw for p in points] == [200]


def test_response_may_be_a_bare_list_or_wrapped_in_data() -> None:
    row = actual_row("2026-01-05T00:00:00Z")
    for body in ([row], {"data": [row]}):
        client, _ = make_client(Script(ok(body)))
        assert len(client.fetch_actuals(DAY, DAY)) == 1


# ----- forecasts -----


def test_forecasts_ask_for_one_publish_day_at_a_time() -> None:
    script = Script(ok([]))
    client, _ = make_client(script)
    client.fetch_forecasts(DAY, DAY)
    assert dict(script.requests[0].url.params) == {
        "publishDateTimeFrom": "2026-01-05T00:00Z",
        "publishDateTimeTo": "2026-01-06T00:00Z",
    }


def test_forecast_rows_seen_in_two_requests_are_stored_once() -> None:
    row = forecast_row("2026-01-06T12:00:00Z", "2026-01-05T23:30:00Z")
    client, _ = make_client(Script(ok([row]), ok([row])))
    assert len(client.fetch_forecasts(date(2026, 1, 5), date(2026, 1, 6))) == 1


def test_forecasts_published_after_their_target_are_kept_as_received() -> None:
    row = forecast_row("2026-01-05T00:00:00Z", "2026-01-05T06:00:00Z")
    client, _ = make_client(Script(ok([row])))
    (point,) = client.fetch_forecasts(DAY, DAY)
    assert point.publish_time > point.start_time
    assert point.publish_time == datetime(2026, 1, 5, 6, tzinfo=UTC)


# ----- retries and failures -----


def test_a_temporary_error_is_retried_and_then_succeeds() -> None:
    script = Script(httpx.Response(503), ok([actual_row("2026-01-05T00:00:00Z")]))
    client, sleeps = make_client(script)
    assert len(client.fetch_actuals(DAY, DAY)) == 1
    assert len(script.requests) == 2
    assert sleeps == [BACKOFF_SECONDS]


def test_backoff_doubles_each_time() -> None:
    script = Script(httpx.Response(429), httpx.Response(503), ok([]))
    client, sleeps = make_client(script)
    client.fetch_actuals(DAY, DAY)
    assert sleeps == [BACKOFF_SECONDS, BACKOFF_SECONDS * 2]


def test_a_network_error_is_retried() -> None:
    script = Script(httpx.ConnectError("boom"), ok([]))
    client, sleeps = make_client(script)
    client.fetch_actuals(DAY, DAY)
    assert len(script.requests) == 2
    assert len(sleeps) == 1


def test_it_gives_up_after_the_maximum_attempts() -> None:
    script = Script(httpx.Response(503))
    client, sleeps = make_client(script)
    with pytest.raises(ElexonError, match="gave up"):
        client.fetch_actuals(DAY, DAY)
    assert len(script.requests) == MAX_ATTEMPTS
    assert len(sleeps) == MAX_ATTEMPTS - 1


def test_a_client_error_is_not_retried() -> None:
    script = Script(httpx.Response(400, text="bad request"))
    client, sleeps = make_client(script)
    with pytest.raises(ElexonError, match="HTTP 400"):
        client.fetch_actuals(DAY, DAY)
    assert len(script.requests) == 1
    assert sleeps == []


# ----- validation -----


def test_a_record_missing_a_field_is_rejected() -> None:
    bad = {"startTime": "2026-01-05T00:00:00Z", "publishTime": "2026-01-05T00:00:00Z"}
    client, _ = make_client(Script(ok([bad])))
    with pytest.raises(ElexonError, match="unexpected record"):
        client.fetch_forecasts(DAY, DAY)


def test_actuals_for_another_fuel_are_rejected() -> None:
    row = actual_row("2026-01-05T00:00:00Z") | {"fuelType": "CCGT"}
    client, _ = make_client(Script(ok([row])))
    with pytest.raises(ElexonError, match="unexpected record"):
        client.fetch_actuals(DAY, DAY)


def test_a_time_without_a_timezone_is_rejected() -> None:
    client, _ = make_client(Script(ok([actual_row("2026-01-05T00:00:00")])))
    with pytest.raises(ElexonError, match="unexpected record"):
        client.fetch_actuals(DAY, DAY)


def test_a_response_that_is_not_a_list_is_rejected() -> None:
    client, _ = make_client(Script(ok({"data": "oops"})))
    with pytest.raises(ElexonError, match="not a list"):
        client.fetch_actuals(DAY, DAY)
