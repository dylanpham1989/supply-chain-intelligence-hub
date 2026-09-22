from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models import User
from app.models.enums import UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.repo = UserRepository(session, tenant_id)

    async def list(self, pagination: PaginationParams) -> tuple[Sequence[User], int]:
        items = await self.repo.list(limit=pagination.size, offset=pagination.offset)
        total = await self.repo.count()
        return items, total

    async def get(self, user_id: UUID) -> User:
        user = await self.repo.get(user_id)
        if user is None:
            # 404 rather than 403 for another tenant's id, so the response does
            # not confirm that the id exists somewhere.
            raise NotFoundError("User not found")
        return user

    async def create(self, payload: UserCreate) -> User:
        if await self.repo.email_exists(str(payload.email)):
            raise ConflictError("That email already has an account here")

        return await self.repo.create(
            email=str(payload.email).lower(),
            password_hash=await hash_password(payload.password),
            full_name=payload.full_name,
            role=payload.role,
        )

    async def update(self, user_id: UUID, payload: UserUpdate, *, acting_user: User) -> User:
        user = await self.get(user_id)

        if user.id == acting_user.id:
            if payload.role is not None and payload.role != user.role:
                raise ForbiddenError("You cannot change your own role")
            if payload.is_active is False:
                raise ForbiddenError("You cannot deactivate yourself")

        demoting_last_admin = (
            payload.role is not None
            and user.role == UserRole.ADMIN
            and payload.role != UserRole.ADMIN
        )
        if demoting_last_admin and not await self._other_admin_exists(user.id):
            raise ForbiddenError("A workspace needs at least one admin")

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.repo.session.flush()
        return user

    async def deactivate(self, user_id: UUID, *, acting_user: User) -> None:
        user = await self.get(user_id)
        if user.id == acting_user.id:
            raise ForbiddenError("You cannot deactivate yourself")
        if user.role == UserRole.ADMIN and not await self._other_admin_exists(user.id):
            raise ForbiddenError("A workspace needs at least one admin")
        user.is_active = False
        await self.repo.session.flush()

    async def _other_admin_exists(self, excluding: UUID) -> bool:
        admins = [
            u
            for u in await self.repo.list(limit=200)
            if u.role == UserRole.ADMIN and u.is_active and u.id != excluding
        ]
        return bool(admins)
