"""Blockers. A blocker that stops the work makes the task BLOCKED and stops the employee's timer; waiting time is then
reported as blocked time, never as working time. When the last blocking problem clears, the task returns to the status
it had before. Every step is an event, so the full history is always available."""

from datetime import datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.collab.models import BLOCKER_TYPES, OPEN_BLOCKER, TaskBlocker, TaskBlockerEvent
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import state_machine as sm
from app.modules.tasks.models import Task, TaskAttachment
from app.modules.tasks.service import can_manage, z
from app.modules.timetracking import queries as tq

# A task can be blocked from any of these; finished, cancelled or in-review work cannot.
BLOCKABLE = ("assigned", "acknowledged", "in_progress", "on_hold", "reopened", "blocked")


def _names(db: Session) -> dict[int, str]:
    return dict(db.execute(select(Employee.user_id, Employee.full_name)).all())


def _event(db: Session, b: TaskBlocker, actor: int | None, event: str, frm: str | None = None, to: str | None = None, note: str | None = None) -> None:
    db.add(TaskBlockerEvent(blocker_id=b.id, actor_user_id=actor, event=event, from_status=frm, to_status=to, note=(note or "").strip() or None))
    db.flush()


def _audit(db: Session, p: Principal, action: str, t: Task, b: TaskBlocker, extra: dict | None = None, request: Request | None = None) -> None:
    after = {"blocker_id": b.id, "title": b.title, "status": b.status, "raised_by_user_id": b.raised_by_user_id,
             "owner_user_id": b.owner_user_id, "blocks_work": b.blocks_work, "priority": t.priority} | (extra or {})  # fmt: skip
    audit.log(db, p.user.id, action, "task", t.id, after=after, request=request, task_id=t.id)


# ---------------------------------------------------------------- permissions


def _visible(p: Principal, t: Task) -> bool:
    return bool(p.employee and p.employee.id == t.assignee_id) or (p.has("blocker.view") and p.can_see("blocker.view", t.assignee_id))


def _manages(p: Principal, t: Task) -> bool:
    return can_manage(p, t, "blocker.manage")


def _is_raiser(p: Principal, b: TaskBlocker) -> bool:
    return p.user.id == b.raised_by_user_id


def _is_owner(p: Principal, b: TaskBlocker) -> bool:
    return b.owner_user_id is not None and p.user.id == b.owner_user_id


def _load(db: Session, p: Principal, blocker_id: int) -> tuple[TaskBlocker, Task]:
    b = db.get(TaskBlocker, blocker_id)
    t = db.get(Task, b.task_id) if b else None
    if b is None or t is None or not (_visible(p, t) or _is_owner(p, b)):  # whoever was asked to solve it must be able to see it
        raise NotFound("Blocker")  # out of scope looks like missing
    return b, t


# ---------------------------------------------------------------- task status effects


def _block_task(db: Session, t: Task, user_id: int, reason: str) -> None:
    if t.status == "blocked":
        return
    t.status_before_block = t.status
    tq.close_running_for_task(db, t, "blocked", clock.utcnow())  # waiting is not working: the clock stops
    sm.force_status(db, t, "blocked", user_id, reason)


def _unblock_if_clear(db: Session, t: Task, user_id: int | None) -> None:
    if t.status != "blocked":
        return
    still = db.scalar(select(func.count(TaskBlocker.id)).where(TaskBlocker.task_id == t.id, TaskBlocker.blocks_work.is_(True), TaskBlocker.status.in_(OPEN_BLOCKER)))
    if still:
        return  # another blocking problem remains
    back = t.status_before_block or "in_progress"
    t.status_before_block = None
    sm.force_status(db, t, back, user_id, "Blocker cleared")


# ---------------------------------------------------------------- the lifecycle


def _attachment_ok(db: Session, p: Principal, t: Task, attachment_id: int | None) -> None:
    if attachment_id is None:
        return
    a = db.get(TaskAttachment, attachment_id)
    if a is None or a.task_id != t.id or a.uploaded_by_user_id != p.user.id:
        raise AppError("INVALID_ATTACHMENT", "Attach the file to this task first, then reference it", 422)


def raise_blocker(db: Session, p: Principal, t: Task, d: dict, request: Request) -> TaskBlocker:
    if p.employee is None or t.assignee_id != p.employee.id:
        raise Forbidden("Only the person this task is assigned to can report a blocker")
    if t.status not in BLOCKABLE:
        raise AppError("TASK_NOT_BLOCKABLE", "This task is finished, cancelled or waiting for review", 409)
    if d["blocker_type"] not in BLOCKER_TYPES:
        raise AppError("INVALID_TYPE", f"Type must be one of: {', '.join(BLOCKER_TYPES)}", 422)
    if len(d["description"].strip()) < 5:
        raise AppError("DESCRIPTION_REQUIRED", "Describe the problem", 422)
    _attachment_ok(db, p, t, d.get("attachment_id"))
    from app.modules.tasks import loop
    head_id = loop.head_id(db, t)
    has_head = bool(head_id and head_id != t.assignee_id)
    b = TaskBlocker(task_id=t.id, raised_by_user_id=p.user.id, blocker_type=d["blocker_type"], title=d["title"].strip(), description=d["description"].strip(),
                    impact=(d.get("impact") or "").strip() or None, blocks_work=bool(d.get("blocks_work", True)),
                    expected_resolution=(d.get("expected_resolution") or "").strip() or None, attachment_id=d.get("attachment_id"),
                    escalated_to_leadership=not has_head)  # fmt: skip
    db.add(b)
    db.flush()
    _event(db, b, p.user.id, "created", None, "open", b.description)
    if b.blocks_work:
        _block_task(db, t, p.user.id, f"Blocked: {b.title}")
    _audit(db, p, "BLOCKER_RAISED", t, b, {"type": b.blocker_type, "impact": b.impact}, request)
    return b


def _move(db: Session, p: Principal, t: Task, b: TaskBlocker, to: str, event: str, note: str | None, action: str, request: Request, extra: dict | None = None) -> None:
    frm = b.status
    b.status = to
    _event(db, b, p.user.id, event, frm, to, note)
    _audit(db, p, action, t, b, extra or {}, request)


def acknowledge(db: Session, p: Principal, blocker_id: int, request: Request) -> TaskBlocker:
    b, t = _load(db, p, blocker_id)
    if not _manages(p, t):
        raise Forbidden()
    if b.status != "open":
        raise Conflict("INVALID_STATE", "Only a new blocker can be acknowledged")
    b.acknowledged_at = clock.utcnow()
    _move(db, p, t, b, "acknowledged", "acknowledged", None, "BLOCKER_ACKNOWLEDGED", request)
    return b


def assign(db: Session, p: Principal, blocker_id: int, owner_employee_id: int, note: str | None, request: Request) -> TaskBlocker:
    b, t = _load(db, p, blocker_id)
    if not _manages(p, t):
        raise Forbidden()
    if b.status not in OPEN_BLOCKER:
        raise Conflict("INVALID_STATE", "This blocker is already resolved")
    target = db.get(Employee, owner_employee_id)
    if target is None or not p.can_see("employee.view", target.id) or target.status == "inactive" or not db.get(User, target.user_id).is_active:
        raise NotFound("Employee")
    b.owner_user_id = target.user_id
    b.acknowledged_at = b.acknowledged_at or clock.utcnow()
    _move(db, p, t, b, "in_progress", "assigned", f"Assigned to {target.full_name}. {note or ''}".strip(), "BLOCKER_ASSIGNED", request,
          {"owner_name": target.full_name})  # fmt: skip
    return b


def start(db: Session, p: Principal, blocker_id: int, request: Request) -> TaskBlocker:
    b, t = _load(db, p, blocker_id)
    if not (_manages(p, t) or _is_owner(p, b)):
        raise Forbidden()
    if b.status not in ("open", "acknowledged"):
        raise Conflict("INVALID_STATE", "Work on this blocker has already started or it is resolved")
    _move(db, p, t, b, "in_progress", "in_progress", None, "BLOCKER_IN_PROGRESS", request)
    return b


def reply(db: Session, p: Principal, blocker_id: int, note: str, request: Request) -> TaskBlocker:
    b, t = _load(db, p, blocker_id)
    if len((note or "").strip()) < 2:
        raise AppError("NOTE_REQUIRED", "Write a reply", 422)
    _event(db, b, p.user.id, "replied", b.status, b.status, note)
    _audit(db, p, "BLOCKER_REPLIED", t, b, {"note": note.strip()[:500]}, request)
    return b


def resolve(db: Session, p: Principal, blocker_id: int, note: str, request: Request) -> TaskBlocker:
    b, t = _load(db, p, blocker_id)
    if not (_manages(p, t) or _is_owner(p, b)):
        raise Forbidden()
    if b.status not in OPEN_BLOCKER:
        raise Conflict("INVALID_STATE", "This blocker is already resolved")
    if len((note or "").strip()) < 3:
        raise AppError("NOTE_REQUIRED", "Say how it was resolved", 422)
    b.resolved_at, b.resolution_note = clock.utcnow(), note.strip()
    _move(db, p, t, b, "resolved", "resolved", note, "BLOCKER_RESOLVED", request, {"note": note.strip()[:500]})
    _unblock_if_clear(db, t, p.user.id)
    return b


def close(db: Session, p: Principal, blocker_id: int, note: str | None, request: Request) -> TaskBlocker:
    """The employee confirms it is sorted (or withdraws it); a manager can also close it."""
    b, t = _load(db, p, blocker_id)
    if not (_manages(p, t) or _is_raiser(p, b)):
        raise Forbidden()
    if b.status == "closed":
        raise Conflict("INVALID_STATE", "This blocker is already closed")
    was_open = b.status in OPEN_BLOCKER
    b.closed_at = clock.utcnow()
    _move(db, p, t, b, "closed", "closed", note or ("Withdrawn" if was_open else None), "BLOCKER_CLOSED", request)
    if was_open:
        _unblock_if_clear(db, t, p.user.id)
    return b


def reopen(db: Session, p: Principal, blocker_id: int, note: str, request: Request) -> TaskBlocker:
    b, t = _load(db, p, blocker_id)
    if not (_manages(p, t) or _is_raiser(p, b)):
        raise Forbidden()
    if b.status not in ("resolved", "closed"):
        raise Conflict("INVALID_STATE", "Only a resolved or closed blocker can be reopened")
    if t.status not in BLOCKABLE:
        raise AppError("TASK_NOT_BLOCKABLE", "The task is finished or cancelled", 409)
    if len((note or "").strip()) < 3:
        raise AppError("NOTE_REQUIRED", "Say why it is still a problem", 422)
    b.resolved_at = b.closed_at = None
    _move(db, p, t, b, "open", "reopened", note, "BLOCKER_REOPENED", request)
    if b.blocks_work:
        _block_task(db, t, p.user.id, f"Blocked again: {b.title}")
    return b


def escalate(db: Session, p: Principal, blocker_id: int, note: str, request: Request) -> TaskBlocker:
    b, t = _load(db, p, blocker_id)
    if not _manages(p, t):
        raise Forbidden()
    if b.status not in OPEN_BLOCKER:
        raise Conflict("INVALID_STATE", "This blocker is already resolved")
    if len((note or "").strip()) < 3:
        raise AppError("NOTE_REQUIRED", "Say why this needs more attention", 422)
    b.escalated_to_leadership = True
    _event(db, b, p.user.id, "escalated", b.status, b.status, note)
    _audit(db, p, "BLOCKER_ESCALATED", t, b, {"note": note.strip()[:500]}, request)
    return b


def close_all_for_task(db: Session, t: Task, user_id: int | None, note: str) -> int:
    """A cancelled task has no problems left to solve."""
    n = 0
    for b in db.scalars(select(TaskBlocker).where(TaskBlocker.task_id == t.id, TaskBlocker.status.in_(OPEN_BLOCKER))):
        frm = b.status
        b.status, b.closed_at = "closed", clock.utcnow()
        _event(db, b, user_id, "closed", frm, "closed", note)
        n += 1
    return n


# ---------------------------------------------------------------- reading


def blocker_dict(db: Session, b: TaskBlocker, events: bool = False, names: dict[int, str] | None = None) -> dict:
    names = names if names is not None else _names(db)
    t = db.get(Task, b.task_id)
    out = {
        "id": b.id, "task": {"id": t.id, "task_no": t.task_no, "title": t.title, "priority": t.priority}, "type": b.blocker_type, "title": b.title,
        "description": b.description, "impact": b.impact, "blocks_work": b.blocks_work, "expected_resolution": b.expected_resolution,
        "status": b.status, "raised_by": names.get(b.raised_by_user_id), "owner": names.get(b.owner_user_id) if b.owner_user_id else None,
        "owner_user_id": b.owner_user_id, "attachment_id": b.attachment_id, "opened_at": z(b.opened_at), "acknowledged_at": z(b.acknowledged_at),
        "resolved_at": z(b.resolved_at), "closed_at": z(b.closed_at), "resolution_note": b.resolution_note,
        "escalated_to_leadership": b.escalated_to_leadership,
        "open_hours": round(((b.resolved_at or b.closed_at or clock.utcnow()) - b.opened_at).total_seconds() / 3600, 1),
    }  # fmt: skip
    if events:
        out["events"] = [
            {"event": e.event, "by": names.get(e.actor_user_id) if e.actor_user_id else "System", "from": e.from_status, "to": e.to_status, "note": e.note, "at": z(e.created_at)}
            for e in db.scalars(select(TaskBlockerEvent).where(TaskBlockerEvent.blocker_id == b.id).order_by(TaskBlockerEvent.id))
        ]  # fmt: skip
    return out


def list_for_task(db: Session, p: Principal, t: Task) -> list[dict]:
    if not _visible(p, t):
        return []
    names = _names(db)
    return [blocker_dict(db, b, True, names) for b in db.scalars(select(TaskBlocker).where(TaskBlocker.task_id == t.id).order_by(TaskBlocker.id.desc()))]


def actions_for(p: Principal, t: Task, b: TaskBlocker) -> list[str]:
    acts: list[str] = []
    manages, raiser, owner = _manages(p, t), _is_raiser(p, b), _is_owner(p, b)
    if b.status in OPEN_BLOCKER:
        acts.append("reply")
        if manages:
            acts += ["assign"] + (["escalate"] if not b.escalated_to_leadership else []) + (["acknowledge"] if b.status == "open" else [])
        if manages or owner:
            acts.append("resolve")
            if b.status in ("open", "acknowledged"):
                acts.append("start")
        if manages or raiser:
            acts.append("close")
    elif b.status == "resolved":
        acts.append("reply")
        if manages or raiser:
            acts += ["close", "reopen"]
    elif b.status == "closed" and (manages or raiser):
        acts.append("reopen")
    return acts


def queue(db: Session, p: Principal, status: str | None, open_only: bool, page: int, page_size: int) -> dict:
    ids = p.scope_employee_ids("blocker.view")
    stmt = select(TaskBlocker).join(Task, Task.id == TaskBlocker.task_id)
    if ids is not None:
        stmt = stmt.where(Task.assignee_id.in_(ids))
    if status:
        stmt = stmt.where(TaskBlocker.status == status)
    elif open_only:
        stmt = stmt.where(TaskBlocker.status.in_(OPEN_BLOCKER))

    is_lead = bool(set(p.roles) & {"owner", "ceo"})
    is_adm = "admin" in p.roles
    if is_lead and not is_adm:
        stmt = stmt.where(TaskBlocker.escalated_to_leadership.is_(True))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(TaskBlocker.opened_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    names = _names(db)
    items = []
    for b in rows:
        d = blocker_dict(db, b, False, names)
        t = db.get(Task, b.task_id)
        d["assignee"] = db.get(Employee, t.assignee_id).full_name
        d["actions"] = actions_for(p, t, b)
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------- waiting time vs working time


def blocked_seconds(db: Session, task_id: int, now: datetime) -> int:
    """Time the task spent genuinely stuck: the UNION of every blocking problem's open periods (two overlapping
    blockers do not count twice). Reported next to, never inside, active working time."""
    intervals: list[tuple[datetime, datetime]] = []
    for b in db.scalars(select(TaskBlocker).where(TaskBlocker.task_id == task_id, TaskBlocker.blocks_work.is_(True))):
        start = None
        for e in db.scalars(select(TaskBlockerEvent).where(TaskBlockerEvent.blocker_id == b.id).order_by(TaskBlockerEvent.id)):
            if e.event in ("created", "reopened") and start is None:
                start = e.created_at
            elif e.event in ("resolved", "closed") and start is not None:
                intervals.append((start, e.created_at))
                start = None
        if start is not None:
            intervals.append((start, now))
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_s is not None:
                total += int((cur_e - cur_s).total_seconds())
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_s is not None:
        total += int((cur_e - cur_s).total_seconds())
    return max(0, total)

