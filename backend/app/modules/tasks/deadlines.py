"""Deadlines: every change is recorded (who, when, why, from/to) and the ORIGINAL deadline is never touched.

Owner/CEO change any deadline; a Manager within their team; a Department Head within their department.
Employees cannot change deadlines: they can only REQUEST an extension, and a manager decides."""

from datetime import date, datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.grace import late_cutoff
from app.modules.audit import service as audit
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks.models import OPEN_STATUSES, ExtensionRequest, Task, TaskDeadlineHistory
from app.modules.tasks.service import can_manage, resolve_due, visible_clause, z
from app.modules.workcal import service as cal

MIN_REASON = 10


def _log(db, p, action, t, before=None, after=None, request=None):
    audit.log(db, p.user.id, action, "task", t.id, before=before, after=after, request=request, task_id=t.id)


def apply_change(db: Session, p: Principal, t: Task, new_due: datetime, reason: str, request: Request | None) -> tuple[TaskDeadlineHistory, list[str]]:
    """The one place a deadline changes. Appends history, bumps the version (which invalidates old reminder schedules),
    counts extensions (later dates only) and leaves original_due_at alone."""
    if t.status not in OPEN_STATUSES:
        raise AppError("TASK_CLOSED", "The deadline of a completed or cancelled task cannot be changed", 409)
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        raise AppError("REASON_REQUIRED", f"Explain the change in at least {MIN_REASON} characters", 422)
    if new_due <= clock.utcnow():
        raise AppError("PAST_DEADLINE", "The new deadline must be in the future", 422)
    if new_due == t.due_at:
        raise AppError("NO_CHANGE", "That is already the deadline", 422)
    previous, kind = t.due_at, ("extension" if new_due > t.due_at else "shorten")
    t.deadline_version += 1
    if kind == "extension":
        t.extension_count += 1
    t.due_at = new_due
    t.version += 1
    hist = TaskDeadlineHistory(task_id=t.id, deadline_version=t.deadline_version, previous_due_at=previous, new_due_at=new_due,
                               changed_by_user_id=p.user.id, change_type=kind, reason=reason)  # fmt: skip
    db.add(hist)
    db.flush()
    _log(db, p, "TASK_DEADLINE_CHANGED", t, before={"due_at": z(previous)},
         after={"due_at": z(new_due), "type": kind, "reason": reason, "version": t.deadline_version, "extension_count": t.extension_count},
         request=request)  # fmt: skip
    return hist, [w for w in (cal.deadline_warning(db, new_due),) if w]


def change_deadline(db: Session, p: Principal, t: Task, due_date: date, reason: str, request: Request):
    if not can_manage(p, t, "task.deadline.edit"):
        raise Forbidden()
    return apply_change(db, p, t, resolve_due(db, due_date), reason, request)


def history(db: Session, t: Task) -> list[dict]:
    names = dict(db.execute(select(Employee.user_id, Employee.full_name)).all())
    rows = db.scalars(select(TaskDeadlineHistory).where(TaskDeadlineHistory.task_id == t.id).order_by(TaskDeadlineHistory.deadline_version)).all()
    return [{"version": h.deadline_version, "type": h.change_type, "previous_due_at": z(h.previous_due_at), "new_due_at": z(h.new_due_at),
             "changed_by": names.get(h.changed_by_user_id), "reason": h.reason, "at": z(h.created_at)} for h in rows]  # fmt: skip


# ---------------------------------------------------------------- extension requests


def request_dict(db: Session, er: ExtensionRequest) -> dict:
    names = dict(db.execute(select(Employee.user_id, Employee.full_name)).all())
    t = db.get(Task, er.task_id)
    return {
        "id": er.id, "task_id": er.task_id, "task_no": t.task_no, "title": t.title, "requested_by": names.get(er.requested_by_user_id),
        "current_due_at": z(t.due_at), "requested_due_at": z(er.requested_due_at), "reason": er.reason, "status": er.status,
        "decided_by": names.get(er.decided_by_user_id), "decision_note": er.decision_note, "approved_due_at": z(er.approved_due_at),
        "created_at": z(er.created_at), "decided_at": z(er.decided_at),
    }  # fmt: skip


def request_extension(db: Session, p: Principal, t: Task, due_date: date, reason: str, request: Request) -> ExtensionRequest:
    if p.employee is None or t.assignee_id != p.employee.id:
        raise Forbidden("Only the person this task is assigned to can ask for more time")
    if t.status not in OPEN_STATUSES:
        raise AppError("TASK_CLOSED", "This task is already finished", 409)
    if len((reason or "").strip()) < MIN_REASON:
        raise AppError("REASON_REQUIRED", f"Explain why you need more time (at least {MIN_REASON} characters)", 422)
    asked = resolve_due(db, due_date)
    if asked <= t.due_at:
        raise AppError("NOT_LATER", "The requested deadline must be later than the current one", 422)
    if db.scalar(select(ExtensionRequest.id).where(ExtensionRequest.task_id == t.id, ExtensionRequest.status == "pending")):
        raise Conflict("REQUEST_PENDING", "You already have a pending request for this task")
    er = ExtensionRequest(task_id=t.id, requested_by_user_id=p.user.id, deadline_version=t.deadline_version,
                          requested_due_at=asked, reason=reason.strip())  # fmt: skip
    db.add(er)
    db.flush()
    _log(db, p, "EXTENSION_REQUESTED", t, after={"request_id": er.id, "requested_due_at": z(asked), "reason": er.reason}, request=request)
    return er


def decide_extension(db: Session, p: Principal, er: ExtensionRequest, approve: bool, note: str | None, due_date: date | None,
                     request: Request) -> tuple[ExtensionRequest, list[str]]:  # fmt: skip
    t = db.get(Task, er.task_id)
    if not can_manage(p, t, "task.deadline.edit"):
        raise NotFound("Request")  # outside scope looks like missing
    if p.employee is not None and t.assignee_id == p.employee.id and p.rank < 100:
        raise Forbidden("You cannot decide on your own extension request")
    if er.status != "pending":
        raise Conflict("ALREADY_DECIDED", "This request was already decided")
    warnings: list[str] = []
    now = clock.utcnow()
    if approve:
        new_due = resolve_due(db, due_date) if due_date else er.requested_due_at
        if new_due <= t.due_at:  # approving must never move a deadline earlier than it already is
            raise Conflict("STALE_REQUEST", "The deadline has already been moved to or beyond that date. Decline this request or pick a later date.")
        hist, warnings = apply_change(db, p, t, new_due, f"Extension approved: {er.reason}", request)
        er.approved_due_at, er.deadline_history_id = new_due, hist.id
    else:
        if len((note or "").strip()) < 3:
            raise AppError("NOTE_REQUIRED", "Tell the employee why the request was declined", 422)
    er.status = "approved" if approve else "rejected"
    er.decided_by_user_id, er.decided_at, er.decision_note = p.user.id, now, (note or "").strip() or None
    _log(db, p, "EXTENSION_DECIDED", t, after={"request_id": er.id, "decision": er.status, "note": note}, request=request)
    return er, warnings


def requests_for_task(db: Session, t: Task) -> list[dict]:
    return [request_dict(db, r) for r in db.scalars(select(ExtensionRequest).where(ExtensionRequest.task_id == t.id).order_by(ExtensionRequest.id.desc()))]


def pending_queue(db: Session, p: Principal) -> list[dict]:
    """Pending requests I am allowed to decide."""
    rows = db.scalars(select(ExtensionRequest).join(Task, Task.id == ExtensionRequest.task_id).where(ExtensionRequest.status == "pending", visible_clause(p)).order_by(ExtensionRequest.id)).all()
    out = []
    for er in rows:
        t = db.get(Task, er.task_id)
        if can_manage(p, t, "task.deadline.edit") and not (p.employee and p.employee.id == t.assignee_id and p.rank < 100):
            out.append(request_dict(db, er) | {"assignee": db.get(Employee, t.assignee_id).full_name})
    return out


# ---------------------------------------------------------------- statistics


def stats(db: Session, p: Principal) -> dict:
    """How often deadlines move, and for whom, within the caller's scope."""
    scope = visible_clause(p)
    base = select(Task).where(scope)
    extended = db.scalar(select(func.count()).select_from(base.where(Task.extension_count > 0).subquery())) or 0
    total = db.scalar(select(func.coalesce(func.sum(Task.extension_count), 0)).where(scope)) or 0
    now = clock.utcnow()
    overdue = db.scalar(select(func.count()).select_from(base.where(Task.status.in_(OPEN_STATUSES), Task.due_at < late_cutoff(now)).subquery())) or 0
    top = db.execute(select(Task.id, Task.task_no, Task.title, Task.extension_count, Task.assignee_id).where(scope, Task.extension_count > 0)
                     .order_by(Task.extension_count.desc(), Task.id).limit(5)).all()  # fmt: skip
    per = db.execute(select(Task.assignee_id, func.sum(Task.extension_count), func.count(Task.id)).where(scope, Task.extension_count > 0)
                     .group_by(Task.assignee_id).order_by(func.sum(Task.extension_count).desc()).limit(10)).all()  # fmt: skip
    names = {e.id: e.full_name for e in db.scalars(select(Employee).where(Employee.id.in_({r[4] for r in top} | {r[0] for r in per})))}
    return {
        "tasks_extended": extended, "extensions_total": int(total), "overdue_tasks": overdue,
        "most_extended": [{"task_id": i, "task_no": n, "title": ti, "extensions": c, "assignee": names.get(a)} for i, n, ti, c, a in top],
        "by_assignee": [{"employee_id": e, "full_name": names.get(e), "extensions": int(x), "tasks": int(c)} for e, x, c in per],
    }  # fmt: skip
