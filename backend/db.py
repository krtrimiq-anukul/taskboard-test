"""The database connection, read from DATABASE_URL.

Locally it comes from backend/.env; on AWS the Deploy tab's binding sets it
(with TLS settings and AWS's certificate file for RDS).
"""
import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set: for local runs, copy backend/.env.example to backend/.env")
    # Some providers hand out postgres://, which SQLAlchemy does not accept.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


@lru_cache(maxsize=1)
def engine() -> Engine:
    # A small pool: on Lambda every running copy keeps its own connections.
    return create_engine(database_url(), pool_pre_ping=True, pool_size=2, max_overflow=3)


def session() -> Session:
    return Session(engine())
