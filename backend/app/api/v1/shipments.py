from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.deps import DbSession, RedisClient, get_current_user, require
from app.models import User
from app.schemas.common import Page
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentFilterQuery,
    ShipmentRead,
    ShipmentUpdate,
)
from app.services.shipment_service import ShipmentService

router = APIRouter(prefix="/shipments", tags=["shipments"])


def _service(
    session: DbSession, redis: RedisClient, user: Annotated[User, Depends(get_current_user)]
) -> ShipmentService:
    return ShipmentService(session, redis, user.tenant_id)


Service = Annotated[ShipmentService, Depends(_service)]
Reader = Annotated[User, Depends(require("shipment:read"))]
Writer = Annotated[User, Depends(require("shipment:write"))]
Remover = Annotated[User, Depends(require("shipment:delete"))]


@router.get("", response_model=Page[ShipmentRead])
async def list_shipments(
    filters: ShipmentFilterQuery, service: Service, _: Reader
) -> Page[ShipmentRead]:
    rows, total = await service.search(filters)
    return Page[ShipmentRead](
        items=[ShipmentRead.model_validate(s) for s in rows],
        total=total,
        page=filters.page,
        size=filters.size,
    )


@router.post("", response_model=ShipmentRead, status_code=status.HTTP_201_CREATED)
async def create_shipment(payload: ShipmentCreate, service: Service, _: Writer) -> ShipmentRead:
    return ShipmentRead.model_validate(await service.create(payload))


@router.get("/{shipment_id}", response_model=ShipmentRead)
async def get_shipment(shipment_id: UUID, service: Service, _: Reader) -> ShipmentRead:
    return ShipmentRead.model_validate(await service.get(shipment_id))


@router.patch("/{shipment_id}", response_model=ShipmentRead)
async def update_shipment(
    shipment_id: UUID, payload: ShipmentUpdate, service: Service, _: Writer
) -> ShipmentRead:
    return ShipmentRead.model_validate(await service.update(shipment_id, payload))


@router.delete("/{shipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shipment(shipment_id: UUID, service: Service, _: Remover) -> Response:
    await service.delete(shipment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
