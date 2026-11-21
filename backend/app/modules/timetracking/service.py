"""Timer use cases: start / pause / stop / switch, heartbeat, check-ins, manual time and corrections.

Rules: server timestamps only; ONE running timer per employee (row lock + a database unique key); sessions of one
employee never overlap; every change to recorded time leaves a correction row, nothing is silently overwritten."""

from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.audit import service as audit
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import state_machine as sm
from app.modules.tasks.models import Task
from app.modules.tasks.service import z
from app.modules.timetracking import queries as q
from app.modules.timetracking.models import TimeCorrection, TimeLog, TimerCheckin

MAX_MANUAL_SECONDS = 16 * 3600
MAX_BACKDATE_DAYS = 14
STARTABLE = ("assigned", "acknowledged", "reopened", "in_progress")


def naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _log(db, p, action, t, before=None, after=None, request=None):
    audit.log(db, p.user.id, action, "task", t.id, before=before, after=after, request=request, task_id=t.id)


def _need_assignee(p: Principal, t: Task) -> Employee:
    if p.employee is None or t.assignee_id != p.employee.id:
        raise Forbidden("Only the person this task is assigned to can do that")
    return p.employee


def enforce_cap(db: Session, log: TimeLog | None, now: datetime) -> bool:
    """Close a forgotten timer once it passes its hard cap. The time is kept but flagged as provisional."""
    if log is None or log.ended_at is not None or now < q.cap_for(db, log):
        return False
    q.close(db, log, q.cap_for(db, log), "auto_timeout", source="auto_closed", confirmed=False)
    audit.log(db, None, "TIMER_AUTO_CLOSED", "time_log", log.id, after={"task_id": log.task_id, "ended_at": z(log.ended_at)}, task_id=log.task_id)
    return True


def _answer_checkins(db: Session, log: TimeLog, response: str, now: datetime) -> None:
    for c in db.scalars(select(TimerCheckin).where(TimerCheckin.time_log_id == log.id, TimerCheckin.responded_at.is_(None))):
        c.responded_at, c.response = now, response


# ---------------------------------------------------------------- timer


def start_timer(db: Session, p: Principal, t: Task, switch: bool, request: Request) -> TimeLog | None:
    emp = _need_assignee(p, t)
    if t.status not in STARTABLE:
        why = {"on_hold": "It is on hold: resume it first.", "blocked": "It is blocked.", "under_review": "It is under review.",
               "completed": "It is already completed.", "cancelled": "It was cancelled."}.get(t.status, "")  # fmt: skip
        raise AppError("TASK_NOT_STARTABLE", f"You cannot start work on this task. {why}".strip(), 409)
    now = clock.utcnow()
    if not get_settings().time_tracking:  # deadlines only: starting just moves the task to "in progress"
        if t.status != "in_progress":
            sm.transition(db, t, "in_progress", p.user.id, "assignee")
        if t.first_started_at is None:
            t.first_started_at = now
            _log(db, p, "TASK_STARTED", t, request=request)
        return None
    q.lock_employee(db, emp.id)
    cur = q.open_session(db, emp.id, lock=True)
    if enforce_cap(db, cur, now):
        cur = None
    if cur is not None:
        other = db.get(Task, cur.task_id)
        if cur.task_id == t.id or not switch:
            raise AppError("TIMER_ALREADY_ACTIVE", "A timer is already running" + (" on this task." if cur.task_id == t.id else f" on {other.task_no}."),
                           409, {"task_id": other.id, "task_no": other.task_no, "title": other.title})  # fmt: skip
        q.close(db, cur, now, "switched")
        _answer_checkins(db, cur, "stop", now)
        _log(db, p, "TIMER_SWITCHED", other, after={"to_task": t.task_no}, request=request)
    if t.status != "in_progress":
        sm.transition(db, t, "in_progress", p.user.id, "assignee")
    if t.first_started_at is None:
        t.first_started_at = now
        _log(db, p, "TASK_STARTED", t, request=request)  # only the FIRST start: managers hear about it once
    log = TimeLog(task_id=t.id, employee_id=emp.id, started_at=now, source="timer", continuous_since=now,
                  last_heartbeat_at=now, created_by_user_id=p.user.id)  # fmt: skip
    try:
        with db.begin_nested():
            db.add(log)
            db.flush()
    except IntegrityError as exc:  # another request got in first: the DB unique key is the last line of defence
        raise AppError("TIMER_ALREADY_ACTIVE", "A timer is already running", 409) from exc
    _log(db, p, "TIMER_STARTED", t, after={"time_log_id": log.id}, request=request)
    return log


def stop_timer(db: Session, p: Principal, t: Task, reason: str, request: Request) -> TimeLog:
    """reason is 'paused' or 'stopped' (both end the running session; 'paused' signals intent to continue)."""
    emp = _need_assignee(p, t)
    if not get_settings().time_tracking:
        raise AppError("TIMER_DISABLED", "Time tracking is switched off. Only deadlines matter.", 409)
    now = clock.utcnow()
    q.lock_employee(db, emp.id)
    cur = q.open_session(db, emp.id, lock=True)
    if enforce_cap(db, cur, now):
        raise AppError("NO_ACTIVE_TIMER", "Your timer was already stopped automatically (it ran past the daily limit). Check your time page.", 409)
    if cur is None or cur.task_id != t.id:
        raise AppError("NO_ACTIVE_TIMER", "No timer is running on this task", 409)
    q.close(db, cur, now, reason)
    _answer_checkins(db, cur, "stop", now)
    _log(db, p, "TIMER_PAUSED" if reason == "paused" else "TIMER_STOPPED", t, after={"time_log_id": cur.id, "seconds": cur.duration_seconds}, request=request)
    return cur


def heartbeat(db: Session, p: Principal) -> dict:
    """Sent every few minutes while the app is open. Only a HINT for the end time of a forgotten timer."""
    if p.employee is None:
        return {"active": False}
    now = clock.utcnow()
    cur = q.open_session(db, p.employee.id)
    if enforce_cap(db, cur, now) or cur is None:
        return {"active": False}
    cur.last_heartbeat_at = now
    return {"active": True}


def continue_session(db: Session, p: Principal) -> dict:
    """'Still working?' -> Continue: the continuous-session clock restarts (check-ins and the cap count from now)."""
    if p.employee is None:
        raise NotFound("Timer")
    now = clock.utcnow()
    q.lock_employee(db, p.employee.id)
    cur = q.open_session(db, p.employee.id, lock=True)
    if enforce_cap(db, cur, now) or cur is None:
        raise AppError("NO_ACTIVE_TIMER", "There is no running timer", 409)
    cur.continuous_since = now
    _answer_checkins(db, cur, "continue", now)
    audit.log(db, p.user.id, "TIMER_CONTINUED", "time_log", cur.id, task_id=cur.task_id)
    return {"continuous_since": z(now), "cap_at": z(q.cap_for(db, cur))}


def active_view(db: Session, p: Principal) -> dict:
    now = clock.utcnow()
    out: dict = {"active": None, "server_time": z(now)}
    if p.employee is None:
        return out
    cur = q.open_session(db, p.employee.id)
    if enforce_cap(db, cur, now):
        cur = None
    if cur is None:
        return out
    t = db.get(Task, cur.task_id)
    pending = db.scalar(select(TimerCheckin).where(TimerCheckin.time_log_id == cur.id, TimerCheckin.responded_at.is_(None)).order_by(TimerCheckin.id.desc()))
    out["active"] = {
        "time_log_id": cur.id, "task": {"id": t.id, "task_no": t.task_no, "title": t.title},
        "started_at": z(cur.started_at), "elapsed_seconds": q.seconds(db, cur, now), "continuous_since": z(cur.continuous_since),
        "cap_at": z(q.cap_for(db, cur)),
        "checkin": {"kind": pending.kind, "at": z(pending.created_at)} if pending else None,
    }  # fmt: skip
    return out


# ---------------------------------------------------------------- summaries


def task_time(db: Session, t: Task) -> dict:
    now = clock.utcnow()
    active = q.active_seconds_map(db, [t.id], now)[t.id]
    end = t.completed_at or t.cancelled_at or now
    logs = db.scalars(select(TimeLog).where(TimeLog.task_id == t.id, TimeLog.status == "approved").order_by(TimeLog.started_at)).all()
    running = next((lg for lg in logs if lg.ended_at is None), None)
    from app.modules.collab.blockers import blocked_seconds  # imported here: collab builds on this module

    return {
        "blocked_seconds": blocked_seconds(db, t.id, now),  # waiting on others: reported beside, never inside, active time
        "estimated_seconds": t.estimated_seconds, "active_seconds": active,
        "provisional_seconds": q.provisional_seconds(db, t.id), "remaining_seconds": max(0, t.estimated_seconds - active),
        "elapsed_seconds": max(0, int((end - t.assigned_at).total_seconds())),
        "assign_to_start_seconds": int((t.first_started_at - t.assigned_at).total_seconds()) if t.first_started_at else None,
        "running": running is not None, "sessions": [session_dict(db, lg, now) for lg in logs],
    }  # fmt: skip


def session_dict(db: Session, lg: TimeLog, now: datetime) -> dict:
    return {
        "id": lg.id, "task_id": lg.task_id, "employee_id": lg.employee_id, "started_at": z(lg.started_at),
        "ended_at": z(lg.ended_at), "seconds": q.seconds(db, lg, now), "source": lg.source, "end_reason": lg.end_reason,
        "confirmed": lg.confirmed, "running": lg.ended_at is None, "note": lg.note,
    }  # fmt: skip


# ---------------------------------------------------------------- manual time + corrections


def _validate_range(start: datetime, end: datetime, now: datetime) -> None:
    if end <= start:
        raise AppError("INVALID_TIME_RANGE", "The end must be after the start", 422)
    if (end - start).total_seconds() > MAX_MANUAL_SECONDS:
        raise AppError("TIME_RANGE_TOO_LONG", "A single entry can be at most 16 hours", 422)
    if end > now:
        raise AppError("TIME_IN_FUTURE", "You cannot record time in the future", 422)
    if start < now - timedelta(days=MAX_BACKDATE_DAYS):
        raise AppError("TIME_TOO_OLD", f"Time can only be added for the last {MAX_BACKDATE_DAYS} days", 422)


def request_missing_time(db: Session, p: Principal, t: Task, start: datetime, end: datetime, reason: str, request: Request) -> TimeCorrection:
    emp = _need_assignee(p, t)
    start, end, now = naive_utc(start), naive_utc(end), clock.utcnow()
    _validate_range(start, end, now)
    if len(reason.strip()) < 5:
        raise AppError("REASON_REQUIRED", "Please explain why this time was not recorded", 422)
    if q.overlapping(db, emp.id, start, end, now):
        raise AppError("TIME_OVERLAP", "That period overlaps time you already recorded", 409)
    c = TimeCorrection(task_id=t.id, employee_id=emp.id, kind="add", new_started_at=start, new_ended_at=end, reason=reason.strip(),
                       requested_by_user_id=p.user.id)  # fmt: skip
    db.add(c)
    db.flush()
    _log(db, p, "TIME_CORRECTION_REQUESTED", t, after={"correction_id": c.id, "from": z(start), "to": z(end)}, request=request)
    return c


def correction_dict(c: TimeCorrection) -> dict:
    return {
        "id": c.id, "task_id": c.task_id, "employee_id": c.employee_id, "time_log_id": c.time_log_id, "kind": c.kind,
        "old_started_at": z(c.old_started_at), "old_ended_at": z(c.old_ended_at), "new_started_at": z(c.new_started_at),
        "new_ended_at": z(c.new_ended_at), "reason": c.reason, "status": c.status, "decision_note": c.decision_note,
        "created_at": z(c.created_at), "decided_at": z(c.decided_at),
    }  # fmt: skip


def _can_decide(p: Principal, employee_id: int) -> bool:
    return p.has("time.correct.approve") and p.can_see("time.correct.approve", employee_id) and not (p.employee and p.employee.id == employee_id)


def decide_correction(db: Session, p: Principal, c: TimeCorrection, approve: bool, note: str | None, request: Request) -> TimeCorrection:
    if not _can_decide(p, c.employee_id):
        raise NotFound("Correction")  # outside scope looks like missing; nobody approves their own time
    if c.status != "pending":
        raise Conflict("ALREADY_DECIDED", "This request was already decided")
    now = clock.utcnow()
    if approve:
        q.lock_employee(db, c.employee_id)
        if q.overlapping(db, c.employee_id, c.new_started_at, c.new_ended_at, now):
            raise AppError("TIME_OVERLAP", "That period now overlaps recorded time; ask the employee to adjust the request", 409)
        db.add(TimeLog(task_id=c.task_id, employee_id=c.employee_id, started_at=c.new_started_at, ended_at=c.new_ended_at,
                       duration_seconds=int((c.new_ended_at - c.new_started_at).total_seconds()), source="manual",
                       end_reason="stopped", confirmed=True, note=c.reason, created_by_user_id=c.requested_by_user_id))  # fmt: skip
    c.status = "approved" if approve else "rejected"
    c.decided_by_user_id, c.decided_at, c.decision_note = p.user.id, now, (note or None)
    audit.log(db, p.user.id, "TIME_CORRECTION_APPROVED" if approve else "TIME_CORRECTION_REJECTED", "time_correction", c.id,
              after={"employee_id": c.employee_id, "note": note}, task_id=c.task_id, request=request)  # fmt: skip
    return c


def adjust_log(db: Session, p: Principal, lg: TimeLog, start: datetime, end: datetime, reason: str, request: Request) -> TimeLog:
    """A manager corrects a closed session directly. The old values are kept in a correction row."""
    if not _can_decide(p, lg.employee_id):
        raise NotFound("Time entry")
    if lg.ended_at is None:
        raise AppError("SESSION_RUNNING", "Stop the timer before adjusting this entry", 409)
    start, end, now = naive_utc(start), naive_utc(end), clock.utcnow()
    _validate_range(start, end, now)
    if len(reason.strip()) < 5:
        raise AppError("REASON_REQUIRED", "A reason is required", 422)
    q.lock_employee(db, lg.employee_id)
    if q.overlapping(db, lg.employee_id, start, end, now, exclude_log_id=lg.id):
        raise AppError("TIME_OVERLAP", "That period overlaps another recorded session", 409)
    db.add(TimeCorrection(task_id=lg.task_id, employee_id=lg.employee_id, time_log_id=lg.id, kind="edit",
                          old_started_at=lg.started_at, old_ended_at=lg.ended_at, new_started_at=start, new_ended_at=end,
                          reason=reason.strip(), status="approved", requested_by_user_id=p.user.id,
                          decided_by_user_id=p.user.id, decided_at=now))  # fmt: skip
    lg.started_at, lg.ended_at, lg.duration_seconds, lg.confirmed = start, end, int((end - start).total_seconds()), True
    audit.log(db, p.user.id, "TIME_LOG_ADJUSTED", "time_log", lg.id, after={"from": z(start), "to": z(end), "reason": reason}, task_id=lg.task_id, request=request)
    return lg


def confirm_log(db: Session, p: Principal, lg: TimeLog, new_end: datetime | None, request: Request) -> TimeLog:
    """The employee confirms an auto-closed session. They may SHORTEN it freely (that only lowers hours);
    anything longer needs a manager (adjust / missing-time request)."""
    if p.employee is None or lg.employee_id != p.employee.id:
        raise NotFound("Time entry")
    if lg.source != "auto_closed" or lg.confirmed or lg.ended_at is None:
        raise Conflict("NOT_UNCONFIRMED", "This entry does not need confirmation")
    end = naive_utc(new_end) if new_end else lg.ended_at
    if end > lg.ended_at:
        raise AppError("EXTENSION_NEEDS_APPROVAL", "You can shorten an auto-closed session here. To add time, request missing time.", 422)
    if end < lg.started_at:
        raise AppError("INVALID_TIME_RANGE", "The end cannot be before the start", 422)
    if end != lg.ended_at:
        db.add(TimeCorrection(task_id=lg.task_id, employee_id=lg.employee_id, time_log_id=lg.id, kind="trim",
                              old_started_at=lg.started_at, old_ended_at=lg.ended_at, new_started_at=lg.started_at, new_ended_at=end,
                              reason="Employee confirmed an auto-closed timer and shortened it", status="approved",
                              requested_by_user_id=p.user.id, decided_by_user_id=p.user.id, decided_at=clock.utcnow()))  # fmt: skip
        lg.ended_at, lg.duration_seconds = end, int((end - lg.started_at).total_seconds())
    lg.confirmed = True
    audit.log(db, p.user.id, "TIME_LOG_CONFIRMED", "time_log", lg.id, after={"ended_at": z(lg.ended_at)}, task_id=lg.task_id, request=request)
    return lg


def unconfirmed_for(db: Session, p: Principal) -> list[dict]:
    if p.employee is None:
        return []
    now = clock.utcnow()
    rows = db.scalars(select(TimeLog).where(TimeLog.employee_id == p.employee.id, TimeLog.source == "auto_closed", TimeLog.confirmed.is_(False),
                                            TimeLog.ended_at.is_not(None), TimeLog.status == "approved").order_by(TimeLog.started_at)).all()  # fmt: skip
    out = []
    for lg in rows:
        t = db.get(Task, lg.task_id)
        hint = lg.last_heartbeat_at or lg.started_at  # last moment we saw the app open: a SUGGESTED end only
        out.append({**session_dict(db, lg, now), "task": {"id": t.id, "task_no": t.task_no, "title": t.title},
                    "suggested_end": z(min(max(hint, lg.started_at), lg.ended_at))})  # fmt: skip
    return out
