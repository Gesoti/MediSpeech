"""Database configuration and session management."""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
    future=True,
)

# Create async session factory
AsyncSessionLocal: sessionmaker = sessionmaker(  # type: ignore[arg-type,call-overload]
    engine,  # type: ignore[arg-type]
    class_=AsyncSession,
    expire_on_commit=False,
    future=True,
)

# Declarative base for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async with AsyncSessionLocal() as session:
        yield session
