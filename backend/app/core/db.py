from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


PK = BigInteger  # BIGINT everywhere (primary and foreign keys must share one type in MySQL)
# Naive UTC timestamps with microsecond precision.
UTCDateTime = mysql.DATETIME(fsp=6)


def make_engine(url: str) -> Engine:
    """MySQL 8 is the only supported database (project decision). No other engine is accepted."""
    if not url.startswith("mysql+pymysql://"):
        raise RuntimeError("Only MySQL is supported: TMS_DATABASE_URL must start with 'mysql+pymysql://'")
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One session per request. Commit on success, roll back on error.

    ALWAYS inject it via `DB` (below), never `Depends(get_db)`: with the default scope FastAPI runs the code
    after `yield` AFTER the response has been sent, so the client could read stale data, and a failed commit
    would surface after a 200 had already gone out. scope="function" runs the commit right after the endpoint
    returns and BEFORE the response is sent."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Use as:  db: Session = DB
DB = Depends(get_db, scope="function")
