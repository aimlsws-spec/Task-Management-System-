"""Clear answers instead of mystery 500s (ADR 008 follow-up).

1. If the database is not at the version this code needs (the usual deployment mistake: new code, old database) every /api call
   answers 503 {"code": "DB_OUTDATED", "message": "... import the new dump or run alembic upgrade head"}.
2. Any unexpected error inside /api answers a JSON 500 that still carries the CORS headers: without this a browser on another
   address only shows "Failed to fetch" and hides the real status.
This runs INSIDE the CORS middleware (see main.py), so both answers are readable by the website."""

import logging
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

log = logging.getLogger("tms.dbguard")
_BASE = Path(__file__).resolve().parents[2]  # folder that holds app/ and alembic/
_state: dict = {"ok": False, "checked": 0.0, "message": ""}


def _config():
    from alembic.config import Config

    cfg = Config()  # no ini file on purpose: env.py would otherwise reset the app's logging
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _current(db) -> str | None:
    return db.scalar(text("select version_num from alembic_version"))


def _auto_upgrade(head: str) -> str | None:
    """Run `alembic upgrade head` once, under a MySQL named lock. Returns None on success, else the reason it did not work."""
    from alembic import command
    from app.core.db import SessionLocal, engine

    try:
        with engine.connect() as lock_conn:  # this connection holds the lock for the whole upgrade
            if not lock_conn.execute(text("select get_lock('tms_migrate', 120)")).scalar():
                return "another worker is upgrading the database"
            try:
                with SessionLocal() as db:
                    if _current(db) == head:  # the other worker finished first
                        return None
                log.warning("database is behind: running alembic upgrade head")
                command.upgrade(_config(), "head")
                return None
            finally:
                lock_conn.execute(text("select release_lock('tms_migrate')"))
    except Exception as exc:  # noqa: BLE001
        log.exception("automatic database upgrade failed")
        return f"{type(exc).__name__}: {exc}"[:300]


def check() -> tuple[bool, str]:
    """(up_to_date, message). A positive answer is remembered; a negative one is re-checked every 10 seconds."""
    if _state["ok"]:
        return True, ""
    now = time.monotonic()
    if _state["message"] and now - _state["checked"] < 10:
        return False, _state["message"]
    try:
        from alembic.script import ScriptDirectory

        from app.core.config import get_settings
        from app.core.db import SessionLocal

        head = ScriptDirectory.from_config(_config()).get_current_head()
        with SessionLocal() as db:
            current = _current(db)
        if current == head:
            _state.update(ok=True, message="")
            return True, ""
        why = ""
        if get_settings().auto_migrate:
            why = _auto_upgrade(head) or ""
            with SessionLocal() as db:
                current = _current(db)
            if current == head:
                _state.update(ok=True, message="")
                return True, ""
        msg = (f"The database is not up to date: it is at version {current}, this app needs {head}."
               + (f" The automatic upgrade did not work ({why})." if why else "")
               + " Import the new tms_db_dump.sql (drop the old tables first) or run: alembic upgrade head")
    except Exception as exc:  # noqa: BLE001 - never block the app because the check itself failed
        log.warning("database version check skipped: %s", exc)
        return True, ""
    _state.update(ok=False, checked=now, message=msg)
    log.error(msg)
    return False, msg


def reset() -> None:
    _state.update(ok=False, checked=0.0, message="")


async def guard(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api"):
        return await call_next(request)
    rid = getattr(request.state, "request_id", None)
    ok, msg = check()
    if not ok:
        return JSONResponse({"code": "DB_OUTDATED", "message": msg, "details": {}, "request_id": rid}, status_code=503)
    try:
        return await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error on %s %s", request.method, path)
        return JSONResponse({"code": "INTERNAL_ERROR", "message": "Something went wrong on the server. Please try again, and give the request_id to your administrator.",
                             "details": {}, "request_id": rid}, status_code=500)
