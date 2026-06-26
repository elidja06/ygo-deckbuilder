# apps/api/db/database.py
"""Initialisation SQLAlchemy 2.0 en mode asynchrone (asyncpg).

Une seule source de vérité pour l'engine et la fabrique de sessions, partagée
entre l'API FastAPI et le worker de synchronisation.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# postgresql+asyncpg://user:password@host:port/dbname
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://ygo:ygo@localhost:5432/ygo",
)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # recycle les connexions mortes (utile pour un worker long)
    echo=False,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,   # on garde les objets utilisables après commit
)


class Base(AsyncAttrs, DeclarativeBase):
    """Base déclarative commune à tous les modèles."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dépendance FastAPI : ouvre une session par requête et la referme."""
    async with SessionLocal() as session:
        yield session
