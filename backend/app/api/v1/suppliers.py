from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.deps import DbSession, RedisClient, get_current_user, require
from app.models import User
from app.schemas.common import Page
from app.schemas.supplier import (
    SupplierCreate,
    SupplierFilterQuery,
    SupplierPerformance,
    SupplierRead,
)
from app.services.supplier_service import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _service(
    session: DbSession, redis: RedisClient, user: Annotated[User, Depends(get_current_user)]
) -> SupplierService:
    return SupplierService(session, redis, user.tenant_id)


Service = Annotated[SupplierService, Depends(_service)]
Reader = Annotated[User, Depends(require("supplier:read"))]
Writer = Annotated[User, Depends(require("supplier:write"))]


@router.get("", response_model=Page[SupplierRead])
async def list_suppliers(
    filters: SupplierFilterQuery, service: Service, _: Reader
) -> Page[SupplierRead]:
    rows, total = await service.search(filters)
    return Page[SupplierRead](
        items=[SupplierRead.model_validate(s) for s in rows],
        total=total,
        page=filters.page,
        size=filters.size,
    )


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(payload: SupplierCreate, service: Service, _: Writer) -> SupplierRead:
    return SupplierRead.model_validate(await service.create(payload))


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier(supplier_id: UUID, service: Service, _: Reader) -> SupplierRead:
    return SupplierRead.model_validate(await service.get(supplier_id))


@router.get("/{supplier_id}/performance", response_model=SupplierPerformance)
async def supplier_performance(
    supplier_id: UUID, service: Service, _: Reader
) -> SupplierPerformance:
    return await service.performance(supplier_id)
