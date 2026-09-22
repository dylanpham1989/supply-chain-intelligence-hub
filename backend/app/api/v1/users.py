from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.deps import DbSession, get_current_user, require
from app.models import User
from app.schemas.common import Page, PaginationQuery
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

Reader = Annotated[User, Depends(require("user:read"))]
Admin = Annotated[User, Depends(require("user:write"))]


def _service(session: DbSession, user: Annotated[User, Depends(get_current_user)]) -> UserService:
    return UserService(session, user.tenant_id)


Service = Annotated[UserService, Depends(_service)]


@router.get("", response_model=Page[UserRead])
async def list_users(pagination: PaginationQuery, service: Service, _: Reader) -> Page[UserRead]:
    users, total = await service.list(pagination)
    return Page[UserRead](
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, service: Service, _: Admin) -> UserRead:
    return UserRead.model_validate(await service.create(payload))


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: UUID, service: Service, _: Reader) -> UserRead:
    return UserRead.model_validate(await service.get(user_id))


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID, payload: UserUpdate, service: Service, actor: Admin
) -> UserRead:
    return UserRead.model_validate(await service.update(user_id, payload, acting_user=actor))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(user_id: UUID, service: Service, actor: Admin) -> None:
    await service.deactivate(user_id, acting_user=actor)
