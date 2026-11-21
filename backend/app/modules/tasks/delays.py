"""Mandatory delay explanations.

When a task is past its deadline the assignee MUST explain. The requirement cannot be dismissed: it stays until a
satisfactory explanation exists and the task cannot be finished without it. Explanations are append-only; a manager
decides on each (accept / ask for clarification / reject / approve a revised deadline / escalate). Accepting an
explanation never completes the task."""

from datetime import date, datetime, timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.grace import late_cutoff
from app.modules.audit import service as audit
from app.modules.audit.settings_service import get_setting
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import deadlines
from app.modules.tasks.models import DelayReason, DelayReview, Task, TaskAttachment, TaskUpdate
from app.modules.tasks.service import can_manage, resolve_due, visible_clause, z
from app.modules.workcal import service as cal

# A task waiting for a reviewer is not the employee's delay any more; finished/cancelled tasks are out of scope.
REQUIRED_STATUSES = ("assigned", "acknowledged", "in_progress", "on_hold", "blocked", "reopened")
DECISIONS = ("accepted", "clarification_requested", "rejected", "revised_deadline_approved", "escalated")
NEEDS_REPLY = ("clarification_requested", "rejected")  # the employee owes a newer explanation
# Leadership (CEO / Owner) only sees a reason once the line (Department Head / Manager) has approved it or sent it up.
RELEASE_DECISIONS = ("accepted", "revised_deadline_approved", "escalated")
LEADERSHIP_RANK = 90


def is_leadership(p: Principal) -> bool:
    """CEO / Owner: they see explanations only after the Department Head or Manager has released them."""
    return p.rank >= LEADERSHIP_RANK
# Escalation tiers after the deadline, counted in WORKING days (level, code, working days)
ESCALATION_TIERS = ((1, "after_1d", 1), (2, "after_3d", 3), (3, "after_7d", 7))


def _log(db, p, action, t, before=None, after=None, request=None):
    audit.log(db, p.user.id, action, "task", t.id, before=before, after=after, request=request, task_id=t.id)


# ---------------------------------------------------------------- when is an explanation required?


def compute_state(db: Session, t: Task, now: datetime, reasons: list[DelayReason], reviews: dict[int, list[DelayReview]]) -> dict:
    """Pure rule. `reasons` = explanations for the CURRENT deadline version, oldest first."""
    overdue = t.status in REQUIRED_STATUSES and t.due_at < late_cutoff(now)
    state = {"overdue": overdue, "required": False, "why": None, "explanations": len(reasons), "latest_decision": None,
             "awaiting_review": False, "escalation_level": 0, "released": False, "escalated": False}  # fmt: skip
    if not overdue:
        return state
    state["escalation_level"] = escalation_level(db, t.due_at, now)
    if not reasons:
        return state | {"required": True, "why": "none_submitted"}
    latest = reasons[-1]
    revs = reviews.get(latest.id, [])
    decision = revs[-1].decision if revs else None
    state |= {"latest_decision": decision, "awaiting_review": not revs, "released": decision in RELEASE_DECISIONS,
              "escalated": decision == "escalated"}  # fmt: skip
    if decision in NEEDS_REPLY:
        return state | {"required": True, "why": "needs_update"}  # the manager asked for more or rejected it
    stale_days = int(get_setting(db, "delay_stale_days"))
    if decision != "accepted" and now - latest.created_at >= timedelta(days=stale_days):
        return state | {"required": True, "why": "stale"}  # nothing new for days and still overdue
    return state


def states_for(db: Session, tasks: list[Task], now: datetime | None = None) -> dict[int, dict]:
    """Batch version for lists (one query each for explanations and decisions)."""
    now = now or clock.utcnow()
    ids = [t.id for t in tasks if t.status in REQUIRED_STATUSES and t.due_at < late_cutoff(now)]
    by_task: dict[int, list[DelayReason]] = {}
    reviews: dict[int, list[DelayReview]] = {}
    if ids:
        for r in db.scalars(select(DelayReason).where(DelayReason.task_id.in_(ids)).order_by(DelayReason.id)):
            by_task.setdefault(r.task_id, []).append(r)
        rids = [r.id for rs in by_task.values() for r in rs]
        if rids:
            for rv in db.scalars(select(DelayReview).where(DelayReview.delay_reason_id.in_(rids)).order_by(DelayReview.id)):
                reviews.setdefault(rv.delay_reason_id, []).append(rv)
    return {t.id: compute_state(db, t, now, [r for r in by_task.get(t.id, []) if r.deadline_version == t.deadline_version], reviews) for t in tasks}


def state_for(db: Session, t: Task, now: datetime | None = None) -> dict:
    return states_for(db, [t], now)[t.id]


# ---------------------------------------------------------------- escalation tiers (working days)


def escalation_times(db: Session, due_at: datetime) -> list[tuple[int, str, datetime]]:
    """When each escalation tier falls due: N WORKING days after the deadline, at the same clock time."""
    local = cal.utc_to_local(db, due_at)
    out = []
    for level, code, n in ESCALATION_TIERS:
        d = cal.add_working_days(db, local.date(), n)
        out.append((level, code, cal.local_to_utc(db, datetime.combine(d, local.time()))))
    return out


def escalation_level(db: Session, due_at: datetime, now: datetime) -> int:
    return sum(1 for _l, _c, when in escalation_times(db, due_at) if when <= now) if due_at < late_cutoff(now) else 0


# ---------------------------------------------------------------- submitting and reading explanations


def _serialize(db: Session, reasons: list[DelayReason]) -> list[dict]:
    names = dict(db.execute(select(Employee.user_id, Employee.full_name)).all())
    revs: dict[int, list[DelayReview]] = {}
    ids = [r.id for r in reasons]
    if ids:
        for rv in db.scalars(select(DelayReview).where(DelayReview.delay_reason_id.in_(ids)).order_by(DelayReview.id)):
            revs.setdefault(rv.delay_reason_id, []).append(rv)
    return [
        {"id": r.id, "deadline_version": r.deadline_version, "kind": r.kind, "reason": r.reason, "progress_pct": r.progress_pct,
         "work_completed": r.work_completed, "remaining_work": r.remaining_work, "blockers": r.blockers_text,
         "expected_completion_at": z(r.expected_completion_at), "attachment_id": r.attachment_id, "at": z(r.created_at),
         "reviews": [{"decision": v.decision, "comment": v.comment, "by": names.get(v.reviewer_user_id), "at": z(v.created_at)} for v in revs.get(r.id, [])]}
        for r in reasons
    ]  # fmt: skip


def released_reason_ids(db: Session, reason_ids: list[int]) -> set[int]:
    """Explanations that a Department Head / Manager has approved (or escalated): the only ones leadership may read."""
    if not reason_ids:
        return set()
    return set(db.scalars(select(DelayReview.delay_reason_id).where(DelayReview.delay_reason_id.in_(reason_ids), DelayReview.decision.in_(RELEASE_DECISIONS))))


def explanations(db: Session, t: Task, p: Principal | None = None) -> list[dict]:
    """Every explanation ever given for this task (newest first), including those for earlier deadlines.
    Leadership (CEO / Owner) gets only the explanations the line has released."""
    rows = list(db.scalars(select(DelayReason).where(DelayReason.task_id == t.id).order_by(DelayReason.id.desc())))
    if p is not None and is_leadership(p) and not (p.employee and p.employee.id == t.assignee_id):
        ok = released_reason_ids(db, [r.id for r in rows])
        rows = [r for r in rows if r.id in ok]
    return _serialize(db, rows)


def can_see_explanations(p: Principal, t: Task) -> bool:
    return bool(p.employee and p.employee.id == t.assignee_id) or (p.has("delay.view") and p.can_see("delay.view", t.assignee_id))


def leadership_may_act(db: Session, p: Principal, t: Task) -> bool:
    """Leadership can decide only on an explanation that has been escalated to them (or already released)."""
    if not is_leadership(p):
        return True
    latest = db.scalar(select(DelayReason.id).where(DelayReason.task_id == t.id).order_by(DelayReason.id.desc()).limit(1))
    return latest is not None and latest in released_reason_ids(db, [latest])


def submit(db: Session, p: Principal, t: Task, d: dict, request: Request) -> DelayReason:
    if p.employee is None or t.assignee_id != p.employee.id:
        raise Forbidden("Only the person this task is assigned to can explain the delay")
    if t.status not in REQUIRED_STATUSES:
        raise AppError("NOT_APPLICABLE", "This task is finished, cancelled or already waiting for review", 409)
    now = clock.utcnow()
    current = [r for r in db.scalars(select(DelayReason).where(DelayReason.task_id == t.id, DelayReason.deadline_version == t.deadline_version))]
    if t.due_at >= late_cutoff(now) and not current:
        raise AppError("NOT_OVERDUE", "The deadline has not passed yet. To ask for more time, request an extension.", 409)
    for field, minimum, label in (("reason", 5, "the reason for the delay"), ("work_completed", 5, "the work completed"), ("remaining_work", 3, "the remaining work")):
        if len((d.get(field) or "").strip()) < minimum:
            raise AppError("FIELD_REQUIRED", f"Please describe {label}", 422)
    expected = resolve_due(db, d["expected_date"])
    if expected <= now:
        raise AppError("EXPECTED_IN_PAST", "The expected completion must be in the future", 422)
    if d.get("attachment_id") is not None:
        a = db.get(TaskAttachment, d["attachment_id"])
        if a is None or a.task_id != t.id or a.uploaded_by_user_id != p.user.id:
            raise AppError("INVALID_ATTACHMENT", "Attach a file to this task first, then reference it", 422)
    row = DelayReason(task_id=t.id, employee_id=p.employee.id, deadline_version=t.deadline_version, kind="update" if current else "initial",
                      reason=d["reason"].strip(), progress_pct=d["progress_pct"], work_completed=d["work_completed"].strip(),
                      remaining_work=d["remaining_work"].strip(), blockers_text=(d.get("blockers") or "").strip() or None,
                      expected_completion_at=expected, attachment_id=d.get("attachment_id"))  # fmt: skip
    db.add(row)
    before = t.progress_pct
    t.progress_pct = d["progress_pct"]
    t.version += 1
    db.add(TaskUpdate(task_id=t.id, author_user_id=p.user.id, progress_pct=d["progress_pct"], note=f"Delay explanation: {row.reason}"[:2000]))
    db.flush()
    _log(db, p, "DELAY_EXPLANATION_SUBMITTED", t, before={"progress_pct": before},
         after={"explanation_id": row.id, "kind": row.kind, "reason": row.reason, "progress_pct": row.progress_pct,
                "expected_completion_at": z(expected)}, request=request)  # fmt: skip
    return row


def auto_explanation_for_completion(db: Session, p: Principal, t: Task, late_reason: str, summary: str) -> DelayReason:
    """Finishing an overdue task: a one-line reason is enough, recorded as a full explanation (nothing remains)."""
    now = clock.utcnow()
    exists = db.scalar(select(DelayReason.id).where(DelayReason.task_id == t.id, DelayReason.deadline_version == t.deadline_version))
    row = DelayReason(task_id=t.id, employee_id=p.employee.id, deadline_version=t.deadline_version, kind="update" if exists else "initial",
                      reason=late_reason.strip(), progress_pct=100, work_completed=summary.strip(), remaining_work="Nothing: the work is complete",
                      blockers_text=None, expected_completion_at=now)  # fmt: skip
    db.add(row)
    db.flush()
    audit.log(db, p.user.id, "DELAY_EXPLANATION_SUBMITTED", "task", t.id, after={"explanation_id": row.id, "reason": row.reason, "with_completion": True}, task_id=t.id)
    return row


# ---------------------------------------------------------------- manager decisions


def review(db: Session, p: Principal, reason: DelayReason, decision: str, comment: str | None, due_date: date | None,
           request: Request) -> tuple[DelayReview, list[str]]:  # fmt: skip
    t = db.get(Task, reason.task_id)
    if not can_manage(p, t, "delay.review"):
        raise NotFound("Explanation")
    if p.employee is not None and t.assignee_id == p.employee.id and p.rank < 100:
        raise Forbidden("You cannot review your own explanation")
    if not leadership_may_act(db, p, t):
        raise NotFound("Explanation")  # not released to leadership yet: it does not exist for them
    if decision not in DECISIONS:
        raise AppError("INVALID_DECISION", f"Decision must be one of: {', '.join(DECISIONS)}", 422)
    latest = db.scalar(select(DelayReason.id).where(DelayReason.task_id == t.id).order_by(DelayReason.id.desc()).limit(1))
    if latest != reason.id:
        raise Conflict("SUPERSEDED", "The employee has sent a newer explanation; review that one")
    if reason.deadline_version != t.deadline_version:
        raise Conflict("OBSOLETE", "The deadline has changed since this explanation was given")
    comment = (comment or "").strip()
    if decision in ("clarification_requested", "rejected") and len(comment) < 3:
        raise AppError("COMMENT_REQUIRED", "Tell the employee what you need", 422)
    hist_id, warnings = None, []
    if decision == "revised_deadline_approved":
        if due_date is None:
            raise AppError("DEADLINE_REQUIRED", "Choose the revised deadline", 422)
        hist, warnings = deadlines.apply_change(db, p, t, resolve_due(db, due_date),
                                                comment or "Revised deadline approved after the delay explanation", request)  # fmt: skip
        hist_id = hist.id
    row = DelayReview(delay_reason_id=reason.id, reviewer_user_id=p.user.id, decision=decision, comment=comment or None, deadline_history_id=hist_id)
    db.add(row)
    db.flush()
    _log(db, p, "DELAY_REVIEWED", t, after={"explanation_id": reason.id, "decision": decision, "comment": comment}, request=request)
    if decision in RELEASE_DECISIONS and not is_leadership(p):  # the line approved it: now leadership may read it
        _log(db, p, "DELAY_RELEASED", t, after={"explanation_id": reason.id, "decision": decision, "reason": reason.reason, "comment": comment}, request=request)
    return row, warnings


def queue(db: Session, p: Principal) -> dict:
    """What a manager has to act on: explanations nobody has answered, and overdue tasks with no (valid) explanation."""
    now = clock.utcnow()
    tasks = db.scalars(select(Task).where(visible_clause(p), Task.status.in_(REQUIRED_STATUSES), Task.due_at < late_cutoff(now)).order_by(Task.due_at)).all()
    tasks = [t for t in tasks if can_manage(p, t, "delay.review")]
    if is_leadership(p):  # leadership only handles what the line escalated to them
        states0 = states_for(db, tasks, now)
        tasks = [t for t in tasks if states0[t.id]["escalated"]]
    states = states_for(db, tasks, now)
    names = {e.id: e.full_name for e in db.scalars(select(Employee).where(Employee.id.in_({t.assignee_id for t in tasks})))} if tasks else {}
    base = lambda t: {"task_id": t.id, "task_no": t.task_no, "title": t.title, "assignee": names.get(t.assignee_id), "priority": t.priority,  # noqa: E731
                      "due_at": z(t.due_at), "extension_count": t.extension_count, "escalation_level": states[t.id]["escalation_level"]}  # fmt: skip
    missing = [base(t) | {"why": states[t.id]["why"]} for t in tasks if states[t.id]["required"] and not is_leadership(p)]
    awaiting = []
    for t in tasks:
        s = states[t.id]
        if (s["awaiting_review"] or (s["escalated"] and is_leadership(p))) and not s["required"] and not (p.employee and p.employee.id == t.assignee_id and p.rank < 100):
            latest = db.scalar(select(DelayReason).where(DelayReason.task_id == t.id, DelayReason.deadline_version == t.deadline_version).order_by(DelayReason.id.desc()).limit(1))
            awaiting.append(base(t) | {"explanation": _serialize(db, [latest])[0]})
    return {"missing": missing, "awaiting": awaiting}
