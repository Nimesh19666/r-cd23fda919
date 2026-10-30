"""Application settings, loaded from environment variables or backend/.env.

Every tunable value lives here so nothing is hard-coded elsewhere.
"""

from datetime import date, time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Reads backend/.env locally; on a host like Vercel the values come from the
    # real environment and the file simply does not exist.
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database (SecretStr stops the password appearing in logs or print())
    database_url: SecretStr

    # Elexon BMRS API
    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"

    # Day-ahead decision assumption: clock time on D-1, in the timezone below.
    decision_cutoff_local: time = time(9, 0)
    decision_timezone: str = "Europe/London"

    # Scope: purchase decisions made in January 2026.
    decision_start_date: date = date(2026, 1, 1)
    decision_end_date: date = date(2026, 1, 31)

    @field_validator("decision_timezone")
    @classmethod
    def _timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def _dates_must_be_ordered(self) -> "Settings":
        if self.decision_start_date > self.decision_end_date:
            raise ValueError("decision_start_date must not be after decision_end_date")
        return self

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.decision_timezone)


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them everywhere."""
    return Settings()
