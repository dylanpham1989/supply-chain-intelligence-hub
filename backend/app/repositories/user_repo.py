from sqlalchemy import func, select

from app.models import User
from app.repositories.base import TenantRepository


class UserRepository(TenantRepository[User]):
    model = User

    async def by_email(self, email: str) -> User | None:
        stmt = self._scoped().where(func.lower(User.email) == email.strip().lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        stmt = select(
            self._scoped().where(func.lower(User.email) == email.strip().lower()).exists()
        )
        return bool((await self.session.execute(stmt)).scalar())
