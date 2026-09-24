from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DbSession, RedisClient, get_current_user, require
from app.models import User
from app.schemas.ask import AskRequest, AskResponse, Citation, InsightFilterQuery, InsightRead
from app.schemas.common import Page
from app.schemas.shipment import ShipmentRead
from app.services.rag_service import RagService

router = APIRouter(tags=["insights"])


def _service(
    session: DbSession, redis: RedisClient, user: Annotated[User, Depends(get_current_user)]
) -> RagService:
    return RagService(session, redis, user.tenant_id)


Service = Annotated[RagService, Depends(_service)]
Asker = Annotated[User, Depends(require("insight:create"))]
Reader = Annotated[User, Depends(require("insight:read"))]


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, service: Service, user: Asker) -> AskResponse:
    result, shipments = await service.ask(payload, user=user)
    return AskResponse(
        question=result.question,
        answer=result.answer,
        route=result.route,
        citations=[Citation(**vars(c)) for c in result.citations],
        filters=result.filters,
        shipments=[ShipmentRead.model_validate(s) for s in shipments],
        model=result.model,
        total_ms=result.total_ms,
    )


@router.get("/insights", response_model=Page[InsightRead])
async def list_insights(
    filters: InsightFilterQuery, service: Service, _: Reader
) -> Page[InsightRead]:
    rows, total = await service.history(filters, route=filters.route)
    return Page[InsightRead](
        items=[InsightRead.model_validate(r) for r in rows],
        total=total,
        page=filters.page,
        size=filters.size,
    )
