from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SessionFactory = async_sessionmaker[AsyncSession]
SessionIterator = AsyncIterator[AsyncSession]


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(
    engine: AsyncEngine,
) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope(
    session_factory: SessionFactory,
) -> SessionIterator:
    async with session_factory() as session:
        yield session
