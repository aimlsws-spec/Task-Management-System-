"""Session math shared by tasks, workload and the timer. Pure reads; the server clock is the only time source."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit.settings_service import get_setting
from app.modules.timetracking.models import TimeLog
from app.modules.workcal import service as cal


def cap_for(db: Session, log: TimeLog) -> datetime:
    """The latest instant an OPEN session may run: `max hours` after it began (or after the last 'Continue'),
    or the next hard cut-off clock time in company timezone (default 22:00), whichever comes first."""
    base = log.continuous_since or log.started_at
    by_length = base + timedelta(hours=float(get_setting(db, "timer_max_session_hours")))
    cutoff_clock = cal.parse_clock(get_setting(db, "timer_hard_cutoff_clock"))
    local = cal.utc_to_local(db, base)
    cutoff_local = datetime.combine(local.date(), cutoff_clock)
    if cutoff_local <= local:  # already past today's cut-off: the next one is tomorrow's
        cutoff_local += timedelta(days=1)
    return min(by_length, cal.local_to_utc(db, cutoff_local))


def effective_end(db: Session, log: TimeLog, now: datetime) -> datetime:
    """Where a session counts up to. An open session never counts beyond its cap, even if no job has closed it yet."""
    if log.ended_at is not None:
        return log.ended_at
    return max(log.started_at, min(now, cap_for(db, log)))


def seconds(db: Session, log: TimeLog, now: datetime) -> int:
    return max(0, int((effective_end(db, log, now) - log.started_at).total_seconds()))


def open_session(db: Session, employee_id: int, lock: bool = False) -> TimeLog | None:
    """The employee's running session. lock=True is a LOCKING read: it sees the latest committed state even inside an
    older transaction snapshot (InnoDB REPEATABLE READ), which matters right after lock_employee()."""
    stmt = select(TimeLog).where(TimeLog.employee_id == employee_id, TimeLog.ended_at.is_(None), TimeLog.status == "approved")
    return db.scalar(stmt.with_for_update() if lock else stmt)


def active_seconds_map(db: Session, task_ids: list[int], now: datetime) -> dict[int, int]:
    """Active working seconds per task: closed approved sessions plus any running one (capped)."""
    if not task_ids:
        return {}
    out = {i: 0 for i in task_ids}
    for tid, total in db.execute(
        select(TimeLog.task_id, func.coalesce(func.sum(TimeLog.duration_seconds), 0))
        .where(TimeLog.task_id.in_(task_ids), TimeLog.status == "approved", TimeLog.ended_at.is_not(None))
        .group_by(TimeLog.task_id)
    ):
        out[tid] = int(total)
    for log in db.scalars(select(TimeLog).where(TimeLog.task_id.in_(task_ids), TimeLog.ended_at.is_(None), TimeLog.status == "approved")):
        out[log.task_id] += seconds(db, log, now)
    return out


def provisional_seconds(db: Session, task_id: int) -> int:
    """Auto-closed time still waiting to be confirmed (counted, but flagged)."""
    return int(
        db.scalar(
            select(func.coalesce(func.sum(TimeLog.duration_seconds), 0)).where(
                TimeLog.task_id == task_id, TimeLog.status == "approved", TimeLog.confirmed.is_(False), TimeLog.ended_at.is_not(None)
            )
        )
        or 0
    )


def overlapping(db: Session, employee_id: int, start: datetime, end: datetime, now: datetime, exclude_log_id: int | None = None) -> TimeLog | None:
    """Any approved session of this employee that overlaps [start, end). An open session counts up to `now`."""
    q = select(TimeLog).where(
        TimeLog.employee_id == employee_id, TimeLog.status == "approved", TimeLog.started_at < end,
        func.coalesce(TimeLog.ended_at, now) > start,
    )  # fmt: skip
    if exclude_log_id is not None:
        q = q.where(TimeLog.id != exclude_log_id)
    return db.scalars(q.limit(1)).first()


# ---------------------------------------------------------------- low-level timer operations


def lock_employee(db: Session, employee_id: int) -> None:
    """Serialize every timer operation of ONE employee (start/stop/switch/corrections) with a row lock."""
    from app.modules.org.models import Employee

    db.execute(select(Employee.id).where(Employee.id == employee_id).with_for_update())


def close(db: Session, log: TimeLog, end: datetime, reason: str, *, source: str | None = None, confirmed: bool | None = None) -> None:
    end = max(end, log.started_at)
    log.ended_at = end
    log.duration_seconds = int((end - log.started_at).total_seconds())
    log.end_reason = reason
    if source is not None:
        log.source = source
    if confirmed is not None:
        log.confirmed = confirmed
    db.flush()  # releases the "one open timer per employee" unique slot right away


def close_running_for_task(db: Session, task, reason: str, now: datetime) -> bool:
    """Stop the assignee's running timer on `task`, if any (hold, complete, cancel, reassign...)."""
    lock_employee(db, task.assignee_id)
    cur = open_session(db, task.assignee_id, lock=True)
    if cur is not None and cur.task_id == task.id:
        close(db, cur, min(now, cap_for(db, cur)) if now > cur.started_at else cur.started_at, reason)
        return True
    return False
