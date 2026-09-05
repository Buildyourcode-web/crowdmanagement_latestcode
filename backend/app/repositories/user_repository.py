from typing import Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.role import Role
from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_username_or_email(self, identifier: str) -> Optional[User]:
        stmt = (
            select(User)
            .where(or_(User.username == identifier, User.email == identifier))
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_role_by_code(self, code: str) -> Optional[Role]:
        stmt = select(Role).where(Role.code == code)
        result = await self.db.execute(stmt)
        return result.scalars().first()
