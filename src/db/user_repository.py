"""Repository helpers for the users table."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> Optional[User]:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, username: str, password: str) -> User:
        existing = await self.get_by_username(username)
        if existing is not None:
            raise ValueError(f"Username '{username}' already exists")
        user = User.create(username=username, password=password)
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_last_login(self, user_id: str) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id).values(last_login=datetime.utcnow())
        )
        await self._session.commit()

    async def deactivate(self, username: str) -> bool:
        result = await self._session.execute(
            update(User).where(User.username == username).values(is_active=False)
        )
        await self._session.commit()
        return result.rowcount > 0

    async def change_password(self, username: str, new_password: str) -> bool:
        user = await self.get_by_username(username)
        if user is None:
            return False
        user.set_password(new_password)
        await self._session.commit()
        return True
