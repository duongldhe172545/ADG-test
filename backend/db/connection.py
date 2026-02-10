"""
Database Connection Setup
PostgreSQL connection with SQLAlchemy async support
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import asynccontextmanager

from backend.config import settings

# Base class for all models
Base = declarative_base()

# Sync engine (for Alembic migrations)
def get_sync_engine():
    """Get synchronous engine for migrations"""
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL not configured")
    
    # Convert postgresql:// to postgresql+psycopg2://
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    return create_engine(url, echo=settings.DEBUG)


# Async engine (for application)
def get_async_engine():
    """Get async engine for application use"""
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL not configured")
    
    # Convert postgresql:// to postgresql+asyncpg://
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return create_async_engine(url, echo=settings.DEBUG)


# Async session factory
def get_async_session_factory():
    """Get async session factory"""
    engine = get_async_engine()
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Dependency for FastAPI
async def get_db():
    """
    Dependency that provides a database session.
    Usage in FastAPI:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL not configured")
    
    AsyncSessionLocal = get_async_session_factory()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context():
    """
    Context manager for database session.
    Usage:
        async with get_db_context() as db:
            ...
    """
    AsyncSessionLocal = get_async_session_factory()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
