"""Probe the Elexon API and print facts about the real data.

Usage (from backend/, venv active):

    python scripts/sample_elexon.py --date 2026-01-05

It downloads one day of FUELHH (actuals, WIND only) and the WINDFOR forecasts published
around that day, saves the raw JSON to data/raw/, and prints what the data looks like.
Parameter names are tried in order because they were not verified offline; the script
says which set worked, so we can hard-code the right one in the real client.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def candidates_fuelhh(day: date) -> list[dict[str, str]]:
    start = day_start(day)
    return [
        {
            "settlementDateFrom": day.isoformat(),
            "settlementDateTo": day.isoformat(),
            "fuelType": "WIND",
        },
        {
            "publishDateTimeFrom": iso(start),
            "publishDateTimeTo": iso(start + timedelta(days=1)),
            "fuelType": "WIND",
        },
    ]


def candidates_windfor(day: date) -> list[dict[str, str]]:
    start = day_start(day)
    return [
        {
            "publishDateTimeFrom": iso(start - timedelta(days=2)),
            "publishDateTimeTo": iso(start + timedelta(days=1)),
        },
        {
            "startTimeFrom": iso(start),
            "startTimeTo": iso(start + timedelta(days=1)),
        },
    ]


def fetch_first_working(
    client: httpx.Client, dataset: str, candidates: list[dict[str, str]]
) -> tuple[list[dict], dict[str, str]]:
    url = f"{BASE_URL}/datasets/{dataset}/stream"
    for params in candidates:
        print(f"\n[{dataset}] trying params: {params}")
        try:
            resp = client.get(url, params=params)
        except httpx.HTTPError as exc:
            print(f"  network error: {exc!r}")
            continue
        print(f"  HTTP {resp.status_code}  url={resp.request.url}")
        if resp.status_code != 200:
            print(f"  body (first 400 chars): {resp.text[:400]!r}")
            continue
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        if rows:
            print(f"  OK: {len(rows)} rows")
            return rows, params
        print("  200 but empty result; trying next param set")
    raise SystemExit(f"No parameter set worked for {dataset}. Paste the output above.")


def show_basics(name: str, df: pd.DataFrame) -> None:
    print(f"\n===== {name} =====")
    print("rows:", len(df))
    print("columns:", list(df.columns))
    print("first 3 rows:\n", df.head(3).to_string())
    print("null counts:\n", df.isna().sum().to_string())


def summarise_actuals(rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    show_basics("FUELHH actuals", df)
    if "fuelType" in df:
        print("fuelType values:", df["fuelType"].unique().tolist())
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df = df.sort_values("startTime")
    print("startTime range:", df["startTime"].min(), "->", df["startTime"].max())
    print("step between startTimes:\n", df["startTime"].diff().dropna().value_counts().to_string())
    print("duplicate startTime rows:", int(df.duplicated("startTime").sum()))
    gen = df["generation"]
    print("generation min / mean / max:", gen.min(), round(gen.mean(), 1), gen.max())


def summarise_forecasts(rows: list[dict], day: date) -> None:
    df = pd.DataFrame(rows)
    show_basics("WINDFOR forecasts", df)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    print("startTime range:", df["startTime"].min(), "->", df["startTime"].max())
    print("publishTime range:", df["publishTime"].min(), "->", df["publishTime"].max())
    print("distinct publishTimes:", df["publishTime"].nunique())
    print("distinct startTimes:", df["startTime"].nunique())
    steps = df.drop_duplicates("startTime").sort_values("startTime")["startTime"].diff()
    print("step between startTimes:\n", steps.dropna().value_counts().to_string())
    print(
        "duplicate (startTime, publishTime) rows:",
        int(df.duplicated(["startTime", "publishTime"]).sum()),
    )
    horizon_h = (df["startTime"] - df["publishTime"]).dt.total_seconds() / 3600
    print(
        "horizon hours (startTime - publishTime) min / median / max:",
        round(horizon_h.min(), 2),
        round(horizon_h.median(), 2),
        round(horizon_h.max(), 2),
    )
    print("negative horizons (published after target):", int((horizon_h < 0).sum()))
    print("forecasts per startTime:\n", df.groupby("startTime").size().describe().to_string())

    # Preview of the selection rule: cutoff = 09:00 UTC on D-1 (January: London = UTC).
    cutoff = day_start(day) - timedelta(hours=15)
    day_end = day_start(day) + timedelta(days=1)
    target = df[(df["startTime"] >= day_start(day)) & (df["startTime"] < day_end)]
    eligible = target[target["publishTime"] <= cutoff]
    print(f"\n--- selection preview for delivery day {day}, cutoff {cutoff} ---")
    print("target-day startTimes in sample:", target["startTime"].nunique())
    print("...with a forecast published by the cutoff:", eligible["startTime"].nunique())


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the Elexon wind datasets.")
    parser.add_argument("--date", default="2026-01-05", help="delivery day, YYYY-MM-DD")
    args = parser.parse_args()
    day = date.fromisoformat(args.date)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60, headers={"Accept": "application/json"}) as client:
        actual_rows, actual_params = fetch_first_working(client, "FUELHH", candidates_fuelhh(day))
        forecast_rows, forecast_params = fetch_first_working(
            client, "WINDFOR", candidates_windfor(day)
        )

    (RAW_DIR / f"fuelhh_wind_{day}.json").write_text(json.dumps(actual_rows, indent=1))
    (RAW_DIR / f"windfor_{day}.json").write_text(json.dumps(forecast_rows, indent=1))

    summarise_actuals(actual_rows)
    summarise_forecasts(forecast_rows, day)

    print("\n===== WORKING PARAMETERS (paste this back) =====")
    print("FUELHH :", actual_params)
    print("WINDFOR:", forecast_params)


if __name__ == "__main__":
    main()
