"""Forgotten-timer guard (SRS section 6). Safe to run as often as you like: closing and check-ins are idempotent.

Browser closure never stops a timer (people work in other tools), so only these things end an unattended session:
  * "Still working?" check-ins after 4 h, after 8 h and in the evening (19:00 company time) - one each per session;
  * a hard cap: 10 h of continuous work or 22:00 company time, whichever is first -> auto-closed and flagged
    PROVISIONAL until the employee confirms (they may only shorten it) or a manager adjusts it.
Phase 6 delivers the check-in prompts as notifications; until then the app shows them from /time/active."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.modules.audit.settings_service import get_setting
from app.modules.notifications.outbox import emit
from app.modules.timetracking.models import TimeLog, TimerCheckin
from app.modules.timetracking.service import enforce_cap
from app.modules.workcal import service as cal


def _add_checkin(db: Session, log: TimeLog, kind: str, now: datetime) -> bool:
    if db.scalar(select(TimerCheckin.id).where(TimerCheckin.time_log_id == log.id, TimerCheckin.kind == kind)):
        return False
    try:
        with db.begin_nested():
            db.add(TimerCheckin(time_log_id=log.id, kind=kind, created_at=now))
            db.flush()
            emit(db, "TIMER_CHECKIN", task_id=log.task_id, payload={"kind": kind, "time_log_id": log.id}, dedupe_key=f"TIMER_CHECKIN:{log.id}:{kind}")
    except IntegrityError:  # a parallel run created it first: exactly what the unique key is for
        return False
    return True


def run_guard(db: Session, now: datetime | None = None) -> dict:
    now = now or clock.utcnow()
    closed = checkins = 0
    evening = cal.parse_clock(get_setting(db, "timer_checkin_clock"))
    for log in db.scalars(select(TimeLog).where(TimeLog.ended_at.is_(None), TimeLog.status == "approved")).all():
        if enforce_cap(db, log, now):
            closed += 1
            continue
        base = log.continuous_since or log.started_at
        due = [kind for hours, kind in ((4, "after_4h"), (8, "after_8h")) if now >= base + timedelta(hours=hours)]
        local_now = cal.utc_to_local(db, now)
        if local_now.time() >= evening and cal.utc_to_local(db, log.started_at) < datetime.combine(local_now.date(), evening):
            due.append("evening")  # still running after the working day ended
        checkins += sum(_add_checkin(db, log, kind, now) for kind in due)
    return {"auto_closed": closed, "checkins_created": checkins}


def unconfirmed_older_than(db: Session, days: int, now: datetime | None = None) -> list[TimeLog]:
    """Auto-closed sessions nobody confirmed for `days` days: the manager is alerted (delivery arrives in Phase 6)."""
    cutoff = (now or clock.utcnow()) - timedelta(days=days)
    return list(
        db.scalars(
            select(TimeLog).where(TimeLog.source == "auto_closed", TimeLog.confirmed.is_(False), TimeLog.ended_at.is_not(None),
                                  TimeLog.ended_at <= cutoff, TimeLog.status == "approved")  # fmt: skip
        )
    )
