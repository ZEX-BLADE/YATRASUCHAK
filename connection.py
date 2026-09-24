"""
SQL persistence layer.

Uses SQLAlchemy so the same code works against:
- Postgres on Render (set the DATABASE_URL env var Render injects when you
  attach a Postgres instance - Render's URL starts with `postgres://`,
  which we normalize to `postgresql://` for SQLAlchemy/psycopg2).
- A local SQLite file for development, when DATABASE_URL isn't set.

`ACTIVE_TRAINS` is kept as a small in-memory cache of the latest telemetry
per train (fast reads for the hot simulation loop / websocket); the SQL
tables are the durable source of truth - every tick is appended to
TelemetryLog, and every train ever looked up is upserted into Train, so
"find a train" is answered from the database and stays consistent no
matter which process/replica served the original request.
"""

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

try:
    from backend.utils.config import BASE_DIR
except ImportError:
    from utils.config import BASE_DIR

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'yatrasuchak.db'}")

# Render (and Heroku-style providers) hand out `postgres://...`, but
# SQLAlchemy's psycopg2 dialect wants `postgresql://...`.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    """Creates any tables that don't exist yet. Safe to call every startup."""
    try:
        from backend.database import models_db  # noqa: F401  (registers models on Base)
    except ImportError:
        from database import models_db  # noqa: F401
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Hot in-memory cache of the latest telemetry per train, kept for fast
# reads in the simulation loop / websocket. The database (TelemetryLog) is
# the durable, queryable record - this is just a cache in front of it.
ACTIVE_TRAINS: dict[str, dict] = {}
