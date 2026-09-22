from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.deps import DbSession, get_current_user, require
from app.models import User
from app.schemas.alert import AlertFilterQuery, AlertRead
from app.schemas.common import Page
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _service(session: DbSession, user: Annotated[User, Depends(get_current_user)]) -> AlertService:
    return AlertService(session, user.tenant_id)


Service = Annotated[AlertService, Depends(_service)]
Reader = Annotated[User, Depends(require("alert:read"))]
Writer = Annotated[User, Depends(require("alert:write"))]


@router.get("", response_model=Page[AlertRead])
async def list_alerts(filters: AlertFilterQuery, service: Service, _: Reader) -> Page[AlertRead]:
    rows, total = await service.search(filters)
    return Page[AlertRead](
        items=[AlertRead.model_validate(a) for a in rows],
        total=total,
        page=filters.page,
        size=filters.size,
    )


@router.get("/unread-count")
async def unread_count(service: Service, _: Reader) -> dict[str, int]:
    return {"unread": await service.unread_count()}


@router.patch("/{alert_id}/read", response_model=AlertRead)
async def mark_read(alert_id: UUID, service: Service, _: Writer) -> AlertRead:
    return AlertRead.model_validate(await service.mark_read(alert_id))


@router.post("/read-all")
async def mark_all_read(service: Service, _: Writer) -> dict[str, int]:
    return {"updated": await service.mark_all_read()}
