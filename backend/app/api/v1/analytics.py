from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.deps import DbSession, RedisClient, get_current_user, require
from app.models import User
from app.schemas.analytics import (
    RiskBreakdown,
    StatusBreakdown,
    Summary,
    Timeseries,
    TopSuppliers,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

Window = Annotated[int, Query(ge=1, le=365, description="Days of history to include")]


def _service(
    session: DbSession, redis: RedisClient, user: Annotated[User, Depends(get_current_user)]
) -> AnalyticsService:
    return AnalyticsService(session, redis, user.tenant_id)


Service = Annotated[AnalyticsService, Depends(_service)]
Reader = Annotated[User, Depends(require("shipment:read"))]


def _mark(response: Response, hit: bool) -> None:
    # Makes the cache observable without a debug endpoint or a log dive.
    response.headers["X-Cache"] = "hit" if hit else "miss"


@router.get("/summary", response_model=Summary)
async def summary(response: Response, service: Service, _: Reader, days: Window = 365) -> Summary:
    value, hit = await service.summary(days)
    _mark(response, hit)
    return value


@router.get("/shipments-by-status", response_model=StatusBreakdown)
async def by_status(
    response: Response, service: Service, _: Reader, days: Window = 365
) -> StatusBreakdown:
    value, hit = await service.by_status(days)
    _mark(response, hit)
    return value


@router.get("/shipments-timeseries", response_model=Timeseries)
async def timeseries(
    response: Response, service: Service, _: Reader, days: Window = 365
) -> Timeseries:
    value, hit = await service.timeseries(days)
    _mark(response, hit)
    return value


@router.get("/top-suppliers", response_model=TopSuppliers)
async def top_suppliers(
    response: Response,
    service: Service,
    _: Reader,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> TopSuppliers:
    value, hit = await service.top_suppliers(limit)
    _mark(response, hit)
    return value


@router.get("/risk-breakdown", response_model=RiskBreakdown)
async def risk_breakdown(
    response: Response, service: Service, _: Reader, days: Window = 365
) -> RiskBreakdown:
    value, hit = await service.risk_breakdown(days)
    _mark(response, hit)
    return value
