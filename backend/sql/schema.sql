-- Wind data schema. Safe to run repeatedly (IF NOT EXISTS).
-- All timestamps are timestamptz and stored in UTC.

-- Actual wind generation (Elexon FUELHH, fuelType = WIND), 30-minute resolution.
CREATE TABLE IF NOT EXISTS wind_actuals (
    start_time     TIMESTAMPTZ      PRIMARY KEY,
    generation_mw  DOUBLE PRECISION NOT NULL,
    ingested_at    TIMESTAMPTZ      NOT NULL DEFAULT now()
);

-- Wind forecasts (Elexon WINDFOR). Many forecasts exist for the same start_time,
-- published at different times, so the key is the pair (start_time, publish_time).
CREATE TABLE IF NOT EXISTS wind_forecasts (
    start_time     TIMESTAMPTZ      NOT NULL,
    publish_time   TIMESTAMPTZ      NOT NULL,
    generation_mw  DOUBLE PRECISION NOT NULL,
    ingested_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (start_time, publish_time)
);

-- Fast lookup of "forecasts published before a cutoff" for a time window.
CREATE INDEX IF NOT EXISTS idx_wind_forecasts_publish_time
    ON wind_forecasts (publish_time);
