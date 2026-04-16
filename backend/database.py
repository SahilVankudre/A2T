"""
Database setup — async SQLAlchemy engine, session factory, Base class.

Depends on:  config.py (B01)
Depended by: models.py (B03), pipeline.py (B08), main.py (B09), migrations/env.py
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import get_settings

settings = get_settings()

# Async engine — used by the FastAPI app for all DB operations.
# pool_size=5 is fine for a single-machine POC.
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set True only when debugging SQL queries
    pool_size=5,
    max_overflow=10,
)

# Session factory — produces async sessions for each request.
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


async def get_db():
    """FastAPI dependency — yields an async DB session per request."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_connection() -> bool:
    """Verify database is reachable. Used by health check endpoint."""
    try:
        async with async_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False