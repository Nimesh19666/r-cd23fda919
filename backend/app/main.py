"""FastAPI application factory.

Run locally:  uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.core.config import get_settings
from app.db import get_engine
from app.repositories.database_source import DatabaseSource
from app.services.report_service import DateOutOfRangeError, MarketConfig, ReportService
from app.web import mount_frontend

logger = logging.getLogger(__name__)


def build_default_service() -> ReportService:
    settings = get_settings()
    config = MarketConfig(
        cutoff_local=settings.decision_cutoff_local,
        tz=settings.tz,
        decision_start_date=settings.decision_start_date,
        decision_end_date=settings.decision_end_date,
    )
    return ReportService(DatabaseSource(get_engine()), config)


def create_app(service: ReportService | None = None, frontend_dir: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Wind Forecast Portal API",
        version="0.1.0",
        description="Day-ahead wind forecasts as the buyer saw them, and how accurate they were.",
    )
    app.state.service = service or build_default_service()
    app.include_router(router)

    @app.exception_handler(DateOutOfRangeError)
    async def out_of_range(_: Request, exc: DateOutOfRangeError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Log only the error type: messages can contain connection details.
        logger.error("Database error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503, content={"detail": "The database is currently unavailable."}
        )

    # Registered last so it can never shadow an API route.
    if frontend_dir is not None and not mount_frontend(app, frontend_dir):
        logger.warning("Frontend build not found in %s; serving the API only.", frontend_dir)

    return app


def create_production_app() -> FastAPI:
    """Entry point for Docker and Heroku: the API plus the built React app."""
    return create_app(frontend_dir=Path(os.environ.get("FRONTEND_DIST_DIR", "static")))
