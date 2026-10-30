"""Database connection helpers. No business logic lives here."""

from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"


@lru_cache
def get_engine() -> Engine:
    """One shared engine. pool_pre_ping drops dead connections (Neon may sleep)."""
    url = get_settings().database_url.get_secret_value()
    return create_engine(url, pool_pre_ping=True)


def apply_schema(engine: Engine | None = None) -> None:
    """Create the tables if they do not exist yet."""
    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))
