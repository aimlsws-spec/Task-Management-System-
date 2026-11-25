"""Background work without Celery, Redis or a permanently running process: everything is stored in the database, and one
pass over every job (`tick`) is run by the cPanel cron job (`python app/jobs/run_once.py`, every minute) or by the Admin's
"Run a pass now" button. Both go through `run_locked`, so two passes can never run at the same time.

Each tick, in order:  reminders scan -> forgotten-timer guard (if enabled) -> relay events to notifications -> send emails.
A failing step is recorded for the Admin and never stops the others."""

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.modules.audit.models import SystemSetting
from app.modules.notifications import mailer, reminders, service
from app.modules.notifications.outbox import emit
from app.modules.timetracking import guard

log = logging.getLogger("tms.scheduler")
LOCK_NAME = "tms_scheduler"


def lock_name(db: Session) -> str:
    """MySQL/MariaDB named locks are SERVER-wide, so the name carries the database: a dev, test and staging database on
    the same server each get their own scheduler instead of blocking one another. (Lock names are limited to 64 characters.)"""
    name = f"{LOCK_NAME}:{db.execute(text('SELECT DATABASE()')).scalar()}"
    return name if len(name) <= 64 else f"{LOCK_NAME}:{hashlib.sha1(name.encode()).hexdigest()[:40]}"


def _step(db: Session, name: str, fn: Callable[[], object]) -> object:
    """Run one step in its own transaction; on failure roll back, record it, carry on."""
    try:
        out = fn()
        db.commit()
        return out
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("scheduler step %s failed", name)
        try:
            service.record_failure(db, name, f"{type(exc).__name__}: {exc}")
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        return None


def _alert_unconfirmed(db: Session, now: datetime) -> int:
    n = 0
    for lg in guard.unconfirmed_older_than(db, 3, now):
        n += emit(db, "TIME_UNCONFIRMED_3D", task_id=lg.task_id, payload={"time_log_id": lg.id}, dedupe_key=f"TIME_UNCONFIRMED_3D:{lg.id}")
    return n


def project_deadlines(db: Session, now: datetime) -> int:
    """Tell everyone on a project (and, when overdue, the CEO/Owner) the day before, on, and after its deadline. Once each."""
    from datetime import time, timedelta

    from sqlalchemy import select

    from app.modules.tasks.models import Project
    from app.modules.workcal import service as cal

    local_dt = cal.utc_to_local(db, now)
    today = local_dt.date()
    local_time = local_dt.time()
    n = 0
    for pr in db.scalars(select(Project).where(Project.status == "active", Project.ends_on.isnot(None), Project.ends_on >= today - timedelta(days=7),
                                               Project.ends_on <= today + timedelta(days=1))):
        if pr.ends_on > today:
            kind = "PROJECT_DEADLINE_TOMORROW"
        elif pr.ends_on < today:
            kind = "PROJECT_OVERDUE"
        else:
            if local_time >= time(15, 30) and local_time < time(18, 30):
                n += emit(db, "PROJECT_DEADLINE_3H", None, None, {"after": {"project_id": pr.id, "project": pr.name, "ends_on": pr.ends_on.isoformat()}},
                          dedupe_key=f"PROJECT_DEADLINE_3H:{pr.id}:{pr.ends_on.isoformat()}")
            kind = "PROJECT_DEADLINE_TODAY"
        n += emit(db, kind, None, None, {"after": {"project_id": pr.id, "project": pr.name, "ends_on": pr.ends_on.isoformat()}},
                  dedupe_key=f"{kind}:{pr.id}:{pr.ends_on.isoformat()}")  # fmt: skip
    return n


def tick(db: Session, now: datetime | None = None, scan: bool = True) -> dict:
    """One pass over every background job. `scan=False` skips the minute-level scanners (used between scans)."""
    explicit_now = now is not None  # tests pass a fixed moment; real runs read the clock again before sending email
    now = now or clock.utcnow()
    result: dict = {}
    if scan:
        result["reminders"] = _step(db, "reminder_scan", lambda: reminders.scan(db, now))
        result["project_deadlines"] = _step(db, "project_deadlines", lambda: project_deadlines(db, now))
        if get_settings().time_tracking:  # the forgotten-timer guard and its alerts only exist with time tracking
            result["timer_guard"] = _step(db, "timer_guard", lambda: guard.run_guard(db, now))
            result["unconfirmed_alerts"] = _step(db, "unconfirmed_alert", lambda: _alert_unconfirmed(db, now))
    pushed = _step(db, "outbox_relay", lambda: service.relay_outbox(db)) or []
    result["notified"] = len(pushed)
    result["emails"] = _step(db, "email_dispatch", lambda: mailer.dispatch_emails(db, now if explicit_now else clock.utcnow()))
    status = db.get(SystemSetting, "scheduler_status")
    value = {"last_tick_at": now.isoformat() + "Z", "scanned": scan}
    if status is None:
        db.add(SystemSetting(key="scheduler_status", value=value))
    else:
        status.value = value
    db.commit()
    return result


def run_locked(factory: Callable[[], Session], now: datetime | None = None, scan: bool = True) -> dict | None:
    """Run ONE pass, but only if no other pass is running (cron, a second cron, or the Admin button).

    The guard is a named lock (GET_LOCK, available in every MySQL and MariaDB version) held on its own connection. The
    server releases it by itself when that connection ends, so a crashed or killed cron run can never leave the jobs locked.
    Returns None when another pass holds the lock (nothing was done), else the result of `tick`."""
    lock_db = factory()
    name: str | None = None
    try:
        name = lock_name(lock_db)
        if lock_db.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": name}).scalar() != 1:
            log.info("another scheduler pass is running; skipping this one")
            return None
        with factory() as db:
            return tick(db, now=now, scan=scan)
    finally:
        try:
            if name is not None:
                lock_db.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": name})
        except Exception:  # noqa: BLE001
            log.warning("could not release the scheduler lock; closing its connection so the server frees it")
            try:
                lock_db.connection().invalidate()  # a closed connection always frees its named locks
            except Exception:  # noqa: BLE001
                pass
        finally:
            lock_db.close()
