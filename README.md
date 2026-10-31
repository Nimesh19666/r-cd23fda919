# Day-ahead wind forecast portal

A small web portal for a UK utility's day-ahead power-buying team. It answers two questions:

1. **What was the latest wind forecast available when the day-ahead decision had to be made?**
2. **How accurate are those forecasts compared with what wind actually produced?**

Data comes only from Elexon BMRS: actual wind generation (`FUELHH`, fuel type `WIND`) and wind forecasts (`WINDFOR`).
Scope: purchase decisions made in **January 2026**, so delivery days run from 2 January to 1 February 2026.

## Live demo

- Portal: **<PORTAL_URL>**
- API: **<API_URL>**/api/health

## What you see

| Screen | Purpose |
|---|---|
| **Day-ahead plan** | Pick a delivery day. See the forecast known at the cutoff, a likely range, and a cautious "count on at least" figure. What actually happened is hidden until you click **Reveal**. |
| **Forecast accuracy** | How far off the forecasts were over the whole month: average miss, whether they lean high or low, by day, by hour of day, and by forecast age. |
| **Assumptions** | The cutoff, data sources, error sign convention and known limits, in plain language. |

## Key finding

Over the 744 hours compared, the forecast had an average miss (MAE) of about **2,022 MW (about 18% of average wind output)** and leaned **high by about 1,746 MW**, over-forecasting on 27 of 31 days.
An alignment test shows this is not a timing slip. The cause is not established. One possibility is that the actuals series does not cover all wind capacity (unverified). This is why the plan page offers a cautious "count on at least" figure.

## How the forecast is chosen (the core rule)

For each hour `T` of delivery day `D`, take the forecast with the **latest `publishTime` at or before the decision cutoff**, which is **09:00 Europe/London on day D-1**.
Forecasts published after the cutoff are never used, so there is no look-ahead bias.

- **Forecast age** is `startTime - publishTime`.
- **Error** is `forecast - actual`. Positive means the forecast was too high.
- Metrics: MAE, RMSE, bias, percentiles of absolute error (P50/P90/P95), and MAE as a percentage of mean actual.
- Hours with no actual are counted as missing, never as zero.

## Assumptions and limitations

- **The 09:00 cutoff is an assumption.** The brief does not state the day-ahead gate time. It is one setting (`DECISION_CUTOFF_LOCAL`).
- **Hourly forecasts vs half-hourly actuals.** We compare only at exact timestamps where both exist (the hour marks).
- **Forecasts published after their target time** are stored but excluded from every calculation.
- **The likely range is in-sample.** It is the middle 80% of January's own errors, so it is slightly optimistic. A fairer test would build it from earlier months.
- **One winter month only.** Accuracy in other seasons may differ.
- The over-forecast bias described above is documented, not corrected.

## Project layout

```
.
├── backend/                     Python 3.13 + FastAPI
│   ├── app/
│   │   ├── main.py              App factory (create_app) and production entry point
│   │   ├── web.py               Serves the built React app (Docker)
│   │   ├── db.py                SQLAlchemy engine and schema helper
│   │   ├── core/config.py       Settings from environment variables
│   │   ├── domain/models.py     ActualPoint, ForecastPoint
│   │   ├── clients/elexon.py    HTTP client: retries, validation, de-duplication
│   │   ├── repositories/        Database reads and writes
│   │   ├── services/
│   │   │   ├── forecast_selection.py   The "latest forecast at cutoff" rule
│   │   │   ├── metrics.py              MAE, RMSE, bias, percentiles
│   │   │   ├── reports.py              Decision view and accuracy report
│   │   │   └── report_service.py       Caching and validation around the reports
│   │   ├── schemas/api.py       Response models
│   │   └── api/routes.py        Thin HTTP routes
│   ├── scripts/                 init_db.py, load_data.py (ingestion), diagnostics
│   ├── sql/schema.sql           Table definitions
│   ├── tests/                   82 tests
│   ├── index.py                 Vercel entry point
│   └── vercel.json
├── frontend/                    React (Vite) + Tailwind + Recharts + TanStack Query
│   └── src/
│       ├── pages/               DecisionPage, AccuracyPage, AssumptionsPage
│       ├── components/          Chart, table, stat strip, query states
│       ├── lib/                 Plain calculation and formatting functions
│       └── api/                 Fetch client and query hooks
├── Dockerfile                   Multi-stage: test, backend, app (API + built React)
└── docker-compose.yml
```

## Run it locally

You need Python 3.11+ (3.13 used), Node 22, and a Postgres database. A free [Neon](https://neon.tech) database works.

### 1. Backend

```bash
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then set DATABASE_URL
```

`DATABASE_URL` must use the `postgresql+psycopg://` prefix, for example
`postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`.

Create the tables and load January 2026 from Elexon:

```bash
python scripts/init_db.py
python scripts/load_data.py
```

Start the API:

```bash
uvicorn app.main:create_app --factory --reload --port 8001
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints. It forwards `/api` to `http://127.0.0.1:8001`.

### 3. Tests and checks

```bash
cd backend
pytest && ruff check . && mypy app
cd ../frontend && npm run lint
```

## Run with Docker

One container serves the API and the built React app on port 8000. Put `DATABASE_URL` in `backend/.env` first.

```bash
docker compose up --build                                       # http://localhost:8000
docker compose --profile tools run --rm test                    # run the tests
docker compose --profile tools run --rm ingest python scripts/init_db.py
docker compose --profile tools run --rm ingest                  # load the data
```

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | Service and database status |
| `GET /api/meta` | Cutoff, timezone, valid date range, assumptions, data freshness |
| `GET /api/decision?delivery_date=YYYY-MM-DD` | The forecast known at the cutoff for each hour, with age and likely range, plus the actuals as a hidden-by-default overlay |
| `GET /api/accuracy` | Summary metrics and breakdowns by day, hour of day and forecast age |

Dates outside the valid range return `422`. Database problems return `503` without leaking connection details.

## Deployment

Deployed on **Vercel** as two projects from this repo:

- **API:** root directory `backend`, FastAPI on Vercel's Python runtime (`backend/index.py`).
- **Portal:** root directory `frontend`, which forwards `/api/*` to the API project (`frontend/vercel.json`).

Environment variables for the API: `DATABASE_URL`, `ELEXON_BASE_URL`, `DECISION_CUTOFF_LOCAL`, `DECISION_TIMEZONE`.
The Docker image is the self-contained alternative for any container host.

## Design notes

- Calculations are **pure functions** (selection, metrics, reports). They are tested without a database or network.
- Data access sits behind a small `DataSource` interface, so tests use an in-memory fake.
- The app is created by a **factory**, with no work done at import time.
- The Elexon client has injectable HTTP and sleep functions, so retry behaviour is tested without waiting.

## AI tools used

This project was built with **Claude (Anthropic)** as a pairing assistant. I used it to:

- explain the problem and its failure modes before writing code,
- design the architecture and the forecast-selection rule,
- generate and refactor code and tests step by step,
- debug errors (for example the Neon connection string and the Vercel deployment),
- draft this README.

I ran every command, tested the results against the live data, reviewed the logic and made the decisions on scope and assumptions myself.

## Ideas for future work

- A confidence selector for the likely range (for example 60%, 80%, 95%).
- A walk-forward range that uses only earlier data, to remove the in-sample optimism.
- A timeline of how the forecast for a given hour changed between publications.
- CSV export of the decision view.
- A simple baseline for comparison (for example "same hour yesterday").
- A wind-level breakdown, to see whether errors are larger at high output.
