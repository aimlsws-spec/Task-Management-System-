"""Tests run against a real MySQL 8 database (the only supported DB). The schema is built by running the
Alembic migrations, so migrations are exercised on every run. Set TMS_TEST_DATABASE_URL (env or backend/.env);
the database name MUST end with `_test` because every table is truncated between tests."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dotenv import dotenv_values

_BACKEND = Path(__file__).resolve().parents[1]
TEST_URL = os.environ.get("TMS_TEST_DATABASE_URL") or dotenv_values(_BACKEND / ".env").get("TMS_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.exit("Set TMS_TEST_DATABASE_URL (MySQL, database name ending in _test). See backend/.env.example.", 2)
_dbname = urlparse(TEST_URL).path.lstrip("/")
if not _dbname.endswith("_test"):
    pytest.exit(f"Refusing to run: test database '{_dbname}' must end with '_test' (tables get truncated).", 2)

# Must be set before the app/settings are imported.
os.environ["TMS_DATABASE_URL"] = TEST_URL
os.environ["TMS_LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["TMS_ENV"] = "test"
os.environ["TMS_OVERDUE_GRACE_MINUTES"] = "0"  # the older suite expects "late" the moment the deadline passes; tests/test_overdue_grace.py sets 40
os.environ["TMS_TIME_TRACKING"] = "true"  # the timer suite needs it; tests/test_no_timer.py turns it off per test
# Tests must NEVER touch real services, whatever backend/.env contains (real SMTP mailbox, scheduler on...).
# Environment variables beat .env, so these win.
for _k, _v in {
    "TMS_EMAIL_BACKEND": "log", "TMS_SMTP_HOST": "", "TMS_SMTP_USER": "", "TMS_SMTP_PASSWORD": "", "TMS_SMTP_PORT": "587",
    "TMS_SMTP_SECURITY": "starttls", "TMS_INLINE_JOBS": "false", "TMS_MAIL_AFTER_REQUEST": "false", "TMS_OTP_ENABLED": "false", "TMS_EMAIL_FROM": "SeaWind Tasks <no-reply@localhost>",
}.items():
    os.environ[_k] = _v

from alembic.config import Config  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.core.security as security  # noqa: E402
import app.models_registry  # noqa: E402,F401
from alembic import command  # noqa: E402
from app.core import clock, ratelimit  # noqa: E402
from app.core.db import Base, get_db, make_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.demo_org import seed_demo  # noqa: E402

# Cheap hashing in tests only.
security._ph = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
security._DUMMY_HASH = security._ph.hash("dummy")

PASSWORD = "Demo@12345!"


_SNAPSHOT: dict[str, list[dict]] = {}


def _data_columns(table):
    return [c for c in table.columns if c.computed is None]  # generated columns cannot be inserted


@pytest.fixture(scope="session")
def engine():
    eng = make_engine(TEST_URL)
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "alembic"))
    command.downgrade(cfg, "base")  # clean slate on the dedicated *_test database
    command.upgrade(cfg, "head")  # builds the schema through the real migrations
    # Seed the demo organization ONCE and remember it; every test then restores this snapshot, which is far
    # faster than re-creating 14 users (and their hierarchy) before each of hundreds of tests.
    with sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)() as s:
        seed_demo(s)
        s.commit()
    with eng.connect() as conn:
        for t in Base.metadata.sorted_tables:
            _SNAPSHOT[t.name] = [dict(r) for r in conn.execute(select(*_data_columns(t))).mappings()]
    yield eng
    eng.dispose()


def _restore_snapshot(engine) -> None:
    tables = Base.metadata.sorted_tables
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for t in reversed(tables):
            conn.execute(t.delete())
        for t in tables:
            if _SNAPSHOT[t.name]:
                conn.execute(t.insert(), _SNAPSHOT[t.name])
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


@pytest.fixture()
def SessionFactory(engine):  # noqa: N802
    _restore_snapshot(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(SessionFactory):
    with SessionFactory() as s:
        yield s


@pytest.fixture()
def seeded(SessionFactory):
    return SessionFactory  # already holds the seeded demo organization


@pytest.fixture()
def client(seeded):
    ratelimit.reset()
    clock.freeze(None)
    application = create_app()

    def _get_db():
        s = seeded()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    application.dependency_overrides[get_db] = _get_db
    with TestClient(application) as c:
        yield c
    clock.freeze(None)


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def as_user(client):
    def _as(name: str) -> dict:
        return login(client, f"{name}@demo.example.com")

    return _as
