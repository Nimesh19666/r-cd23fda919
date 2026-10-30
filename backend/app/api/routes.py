"""HTTP routes. No logic here: validate input, call the service, return the result."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.schemas.api import AccuracyResponse, DecisionResponse, HealthResponse, MetaResponse
from app.services.report_service import ReportService

router = APIRouter(prefix="/api")


def get_service(request: Request) -> ReportService:
    service: ReportService = request.app.state.service
    return service


ServiceDep = Annotated[ReportService, Depends(get_service)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(service: ServiceDep) -> HealthResponse:
    """Liveness plus database reachability. Never fails: reports 'degraded' instead."""
    return service.health()


@router.get("/meta", response_model=MetaResponse, tags=["system"])
def meta(service: ServiceDep) -> MetaResponse:
    """Assumptions, scope, data freshness and caveats shown in the app."""
    return service.meta()


@router.get("/decision", response_model=DecisionResponse, tags=["forecast"])
def decision(
    delivery_date: Annotated[date, Query(description="Delivery day, YYYY-MM-DD")],
    service: ServiceDep,
) -> DecisionResponse:
    """The forecast the buyer could see at the cutoff on the day before delivery_date."""
    return service.decision(delivery_date)


@router.get("/accuracy", response_model=AccuracyResponse, tags=["forecast"])
def accuracy(service: ServiceDep) -> AccuracyResponse:
    """How accurate the decision-time forecasts were across the whole backtest period."""
    return service.accuracy()
