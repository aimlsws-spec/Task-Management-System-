"""The employee's side of a task (progress, hold, finish) and management's side of finished work
(verify, revert, review). The assignee completes their own work with an assurance; review is optional and a
manager can send finished work back at any time (e.g. QA finds the feature broken)."""

import re

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden
from app.modules.audit import service as audit
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import loop, projects
from app.modules.tasks import state_machine as sm
from app.modules.tasks.models import (
    TERMINAL,
    Task,
    TaskCompletionAssurance,
    TaskOwnership,
    TaskRevert,
    TaskUpdate,
    TaskVerification,
)
from app.modules.tasks.service import can_manage, z
from app.modules.timetracking import queries as q

REVERT_REASONS = ("qa_defect", "incomplete", "requirement_change", "other")


def _log(db, p, action, t, before=None, after=None, request=None):
    audit.log(db, p.user.id, action, "task", t.id, before=before, after=after, request=request, task_id=t.id)


def _assignee_only(p: Principal, t: Task) -> None:
    if p.employee is None or t.assignee_id != p.employee.id:
        raise Forbidden("Only the person this task is assigned to can do that")


def _no_self(p: Principal, t: Task, what: str) -> None:
    """Nobody verifies, reviews or reverts their own work (the Owner is the one exception)."""
    if p.employee is not None and p.employee.id == t.assignee_id and p.rank < 100:
        raise Forbidden(f"You cannot {what} your own work")


def attempts(db: Session, t: Task) -> int:
    return db.scalar(select(func.count(TaskCompletionAssurance.id)).where(TaskCompletionAssurance.task_id == t.id)) or 0


# ---------------------------------------------------------------- progress / hold


def add_progress(db: Session, p: Principal, t: Task, pct: int, note: str, request: Request) -> TaskUpdate:
    _assignee_only(p, t)
    if t.status not in ("acknowledged", "in_progress", "on_hold", "blocked", "reopened"):
        raise AppError("PROGRESS_NOT_ALLOWED", "Start the task before reporting progress", 409)
    if len(note.strip()) < 3:
        raise AppError("NOTE_REQUIRED", "Add a short note about what was done", 422)
    before = t.progress_pct
    u = TaskUpdate(task_id=t.id, author_user_id=p.user.id, progress_pct=pct, note=note.strip())
    db.add(u)
    t.progress_pct = pct
    t.version += 1
    db.flush()
    _log(db, p, "TASK_PROGRESS", t, before={"progress_pct": before}, after={"progress_pct": pct, "note": note.strip()}, request=request)
    return u


def hold(db: Session, p: Principal, t: Task, reason: str, request: Request) -> None:
    by_manager = not (p.employee and p.employee.id == t.assignee_id)
    if by_manager and not can_manage(p, t, "task.edit"):
        raise Forbidden()
    if len(reason.strip()) < 3:
        raise AppError("REASON_REQUIRED", "A reason is required to put a task on hold", 422)
    sm.transition(db, t, "on_hold", p.user.id, "manager" if by_manager else "assignee", reason.strip())
    q.close_running_for_task(db, t, "on_hold", clock.utcnow())
    _log(db, p, "TASK_ON_HOLD", t, after={"reason": reason.strip()}, request=request)


def unhold(db: Session, p: Principal, t: Task, request: Request) -> None:
    by_manager = not (p.employee and p.employee.id == t.assignee_id)
    if by_manager and not can_manage(p, t, "task.edit"):
        raise Forbidden()
    sm.transition(db, t, "in_progress", p.user.id, "manager" if by_manager else "assignee", "Resumed from hold")
    _log(db, p, "TASK_RESUMED_FROM_HOLD", t, request=request)


# ---------------------------------------------------------------- finishing work


def _assurance(db: Session, p: Principal, t: Task, d: dict) -> TaskCompletionAssurance:
    _assignee_only(p, t)
    if t.status != "in_progress":
        raise Conflict("NOT_IN_PROGRESS", "Start the task before finishing it" if t.status in ("assigned", "acknowledged", "reopened") else f"A {t.status.replace('_', ' ')} task cannot be finished")
    if len(d["summary"].strip()) < 5:
        raise AppError("SUMMARY_REQUIRED", "Describe what was done", 422)
    if d["tested"] is False and len((d.get("test_notes") or "").strip()) < 3:
        raise AppError("TEST_NOTES_REQUIRED", "If it is not tested, explain why or what remains to test", 422)
    if d.get("evidence_url") and not re.match(r"^https?://\S+$", d["evidence_url"]):
        raise AppError("INVALID_EVIDENCE_URL", "Evidence must be a web link (http/https)", 422)
    now = clock.utcnow()
    from app.modules.tasks import delays  # imported here: delays builds on tasks.service

    state = delays.state_for(db, t, now)
    late_reason = (d.get("late_reason") or "").strip()
    if state["required"] and len(late_reason) < 5:
        raise AppError("DELAY_EXPLANATION_REQUIRED", "This task is overdue. Explain the delay before finishing it.", 409,
                       {"why": state["why"]})  # fmt: skip
    active = q.active_seconds_map(db, [t.id], now)[t.id]
    if get_settings().time_tracking and active <= 0 and len((d.get("no_time_reason") or "").strip()) < 5:
        raise AppError("TIME_REQUIRED", "No time is recorded on this task. Track time, or explain why none was needed.", 422)
    q.close_running_for_task(db, t, "completed", now)
    if state["required"]:  # a one-line reason given while finishing is recorded as a proper explanation
        delays.auto_explanation_for_completion(db, p, t, late_reason, d["summary"])
    row = TaskCompletionAssurance(
        task_id=t.id, employee_id=p.employee.id, attempt_no=attempts(db, t) + 1, summary=d["summary"].strip(), tested=d["tested"],
        test_notes=(d.get("test_notes") or "").strip() or None, evidence_url=d.get("evidence_url") or None,
        no_time_reason=(d.get("no_time_reason") or "").strip() or None,
    )  # fmt: skip
    db.add(row)
    db.flush()
    return row


def _submit_to_chain(db: Session, p: Principal, t: Task, d: dict, request: Request) -> None:
    """Done -> QA (if any) -> head (if any) -> CEO/Owner. It is only Completed after leadership reviews it (ADR 003, 006)."""
    a = _assurance(db, p, t, d)
    sm.transition(db, t, "under_review", p.user.id, "assignee", "Submitted for review")
    t.submitted_at, t.progress_pct = clock.utcnow(), 100
    t.review_stage = projects.first_stage(db, t)
    _log(db, p, "TASK_SUBMITTED", t, after={"attempt": a.attempt_no, "summary": a.summary, "tested": a.tested}, request=request)
    projects.announce_stage(db, p, t, request)


def complete(db: Session, p: Principal, t: Task, d: dict, request: Request) -> None:
    if loop.has_chain(db, t):
        return _submit_to_chain(db, p, t, d, request)
    if t.requires_review:
        raise AppError("REVIEW_REQUIRED", "This task needs a review: use 'Submit for review'", 409)
    a = _assurance(db, p, t, d)
    sm.transition(db, t, "completed", p.user.id, "assignee", "Completed by assignee")
    t.completed_at, t.progress_pct = clock.utcnow(), 100
    _log(db, p, "TASK_COMPLETED", t, after={"attempt": a.attempt_no, "summary": a.summary, "tested": a.tested,
                                           "late": t.completed_at > t.due_at}, request=request)  # fmt: skip


def submit_for_review(db: Session, p: Principal, t: Task, d: dict, request: Request) -> None:
    if loop.has_chain(db, t):
        return _submit_to_chain(db, p, t, d, request)
    a = _assurance(db, p, t, d)
    sm.transition(db, t, "under_review", p.user.id, "assignee", "Submitted for review")
    t.submitted_at, t.progress_pct = clock.utcnow(), 100
    _log(db, p, "TASK_SUBMITTED", t, after={"attempt": a.attempt_no, "summary": a.summary, "tested": a.tested}, request=request)


# ---------------------------------------------------------------- management: review / verify / revert


def _need_manage_verify(p: Principal, t: Task) -> None:
    if not can_manage(p, t, "task.verify"):
        raise Forbidden()


def _mark_verified(db: Session, p: Principal, t: Task, note: str | None) -> None:
    t.verified_at, t.verified_by_user_id = clock.utcnow(), p.user.id
    db.add(TaskVerification(task_id=t.id, attempt_no=attempts(db, t), verified_by_user_id=p.user.id, note=(note or "").strip() or None))
    db.flush()


def verify(db: Session, p: Principal, t: Task, note: str | None, request: Request) -> None:
    _need_manage_verify(p, t)
    _no_self(p, t, "verify")
    if t.status != "completed":
        raise Conflict("NOT_COMPLETED", "Only completed tasks can be verified")
    if t.verified_at is not None:
        raise Conflict("ALREADY_VERIFIED", "This completion is already verified")
    _mark_verified(db, p, t, note)
    t.version += 1
    _log(db, p, "TASK_VERIFIED", t, after={"note": note}, request=request)


def _send_back(db: Session, p: Principal, t: Task, code: str, reason: str, found_by: str | None, bug_sheet_url: str | None = None) -> None:
    if code not in REVERT_REASONS:
        raise AppError("INVALID_REASON_CODE", f"Reason must be one of: {', '.join(REVERT_REASONS)}", 422)
    if len(reason.strip()) < 5:
        raise AppError("REASON_REQUIRED", "Explain what is wrong so the assignee can fix it", 422)
    db.add(TaskRevert(task_id=t.id, attempt_no=max(attempts(db, t), 1), reverted_by_user_id=p.user.id, reason_code=code,
                      reason=reason.strip(), found_by=(found_by or "").strip() or None,
                      bug_sheet_url=(bug_sheet_url or "").strip() or None))  # fmt: skip
    t.revert_count += 1
    t.review_stage = None
    t.completed_at = t.submitted_at = t.verified_at = t.verified_by_user_id = None
    db.flush()  # autoflush is off; the response reads these rows straight back


def revert(db: Session, p: Principal, t: Task, code: str, reason: str, found_by: str | None, request: Request, bug_sheet_url: str | None = None) -> None:
    """Send finished work back (e.g. QA found the feature not working). Allowed any time after completion."""
    _need_manage_verify(p, t)
    _no_self(p, t, "revert")
    sm.transition(db, t, "reopened", p.user.id, "manager", f"Reverted: {reason.strip()}")
    _send_back(db, p, t, code, reason, found_by, bug_sheet_url)
    _log(db, p, "TASK_REVERTED", t, after={"reason_code": code, "reason": reason.strip(), "found_by": found_by, "bug_sheet_url": bug_sheet_url, "revert_count": t.revert_count}, request=request)


STAGE_WHO = {"qa": "the QA", "head": "the head", "leadership": "the CEO or Owner"}


def _review_in_chain(db: Session, p: Principal, t: Task, approve: bool, code: str | None, comment: str | None, request: Request, bug_sheet_url: str | None = None) -> None:
    if t.status != "under_review":
        raise Conflict("NOT_UNDER_REVIEW", "Only a task under review can be reviewed")
    if not projects.my_turn_to_review(db, p, t):
        raise Forbidden(f"This step is for {STAGE_WHO.get(t.review_stage, 'someone else')}")
    stage = t.review_stage
    if not approve:  # QA finding bugs is the common case: the assignee fixes them and submits again, and QA tests again
        code = code or ("qa_defect" if stage == "qa" else "incomplete")
        sm.transition(db, t, "reopened", p.user.id, "manager", f"Review rejected: {comment}")
        _send_back(db, p, t, code, comment or "", "QA" if stage == "qa" else None, bug_sheet_url)
        _log(db, p, "TASK_REVIEW_REJECTED", t, after={"reason_code": code, "reason": comment, "stage": stage, "bug_sheet_url": bug_sheet_url}, request=request)
        return
    nxt = loop.next_stage(db, t, stage)
    if nxt is not None:  # this stage is done: the next person is told it is their turn
        t.review_stage = nxt
        t.version += 1
        _log(db, p, "TASK_QA_APPROVED" if stage == "qa" else "TASK_HEAD_APPROVED", t, after={"note": comment}, request=request)
        projects.announce_stage(db, p, t, request)
        return
    sm.transition(db, t, "completed", p.user.id, "manager", "Review approved")
    t.review_stage, t.completed_at = None, clock.utcnow()
    _mark_verified(db, p, t, comment)
    _log(db, p, "TASK_REVIEW_APPROVED", t, after={"note": comment}, request=request)
    if t.project_id:
        projects.check_ready(db, projects.get_project(db, t.project_id))


def review(db: Session, p: Principal, t: Task, approve: bool, code: str | None, comment: str | None, request: Request, bug_sheet_url: str | None = None) -> None:
    if t.review_stage:
        return _review_in_chain(db, p, t, approve, code, comment, request, bug_sheet_url)
    _need_manage_verify(p, t)
    _no_self(p, t, "review")
    if t.status != "under_review":
        raise Conflict("NOT_UNDER_REVIEW", "Only a task under review can be reviewed")
    if approve:
        sm.transition(db, t, "completed", p.user.id, "manager", "Review approved")
        t.completed_at = clock.utcnow()
        _mark_verified(db, p, t, comment)
        _log(db, p, "TASK_REVIEW_APPROVED", t, after={"note": comment}, request=request)
    else:
        sm.transition(db, t, "reopened", p.user.id, "manager", f"Review rejected: {comment}")
        _send_back(db, p, t, code or "incomplete", comment or "", None, bug_sheet_url)
        _log(db, p, "TASK_REVIEW_REJECTED", t, after={"reason_code": code or "incomplete", "reason": comment, "bug_sheet_url": bug_sheet_url}, request=request)


# ---------------------------------------------------------------- read models


def detail_extras(db: Session, t: Task) -> dict:
    updates = db.scalars(select(TaskUpdate).where(TaskUpdate.task_id == t.id).order_by(TaskUpdate.id.desc()).limit(20)).all()
    assurances = db.scalars(select(TaskCompletionAssurance).where(TaskCompletionAssurance.task_id == t.id).order_by(TaskCompletionAssurance.id)).all()
    reverts = db.scalars(select(TaskRevert).where(TaskRevert.task_id == t.id).order_by(TaskRevert.id)).all()
    return {
        "revert_count": t.revert_count, "verified_at": z(t.verified_at), "submitted_at": z(t.submitted_at),
        "updates": [{"progress_pct": u.progress_pct, "note": u.note, "at": z(u.created_at)} for u in updates],
        "assurances": [{"attempt": a.attempt_no, "summary": a.summary, "tested": a.tested, "test_notes": a.test_notes,
                        "evidence_url": a.evidence_url, "no_time_reason": a.no_time_reason, "at": z(a.created_at)} for a in assurances],
        "reverts": [{"attempt": r.attempt_no, "reason_code": r.reason_code, "reason": r.reason, "found_by": r.found_by,
                     **({"bug_sheet_url": r.bug_sheet_url} if r.bug_sheet_url else {}), "at": z(r.created_at)} for r in reverts],
    }  # fmt: skip



# ---------------------------------------------------------------- Department Head takes responsibility


def can_take_ownership(db: Session, p: Principal, t: Task) -> bool:
    """A Department Head or SubHead, for an open task held by someone else in their own department."""
    if not (set(p.roles) & {"department_head", "sub_head"}) or p.employee is None or t.assignee_id == p.employee.id:
        return False
    if t.status in TERMINAL or not p.can_see("task.view", t.assignee_id):
        return False
    return db.scalar(select(TaskOwnership.id).where(TaskOwnership.task_id == t.id, TaskOwnership.employee_id == p.employee.id)) is None


def take_ownership(db: Session, p: Principal, t: Task, note: str | None, request) -> TaskOwnership:
    if not can_take_ownership(db, p, t):
        raise AppError("OWNERSHIP_NOT_ALLOWED", "Only the Department Head or SubHead of the person holding an open task can take ownership of it, once", 409)
    row = TaskOwnership(task_id=t.id, employee_id=p.employee.id, user_id=p.user.id, note=(note or "").strip() or None)
    db.add(row)
    db.flush()
    audit.log(db, p.user.id, "TASK_OWNERSHIP_TAKEN", "task", t.id, after={"head": p.employee.full_name, "note": row.note}, request=request, task_id=t.id)
    return row


def ownership_for(db: Session, t: Task) -> dict:
    """Who is accountable for this task above the assignee: the department head, and who has taken responsibility."""
    from app.modules.org.models import Department

    head_id = db.scalar(select(Department.head_employee_id).where(Department.id == t.department_id))
    names = dict(db.execute(select(Employee.id, Employee.full_name)).all())
    rows = db.scalars(select(TaskOwnership).where(TaskOwnership.task_id == t.id).order_by(TaskOwnership.id)).all()
    return {"accountable_head": {"id": head_id, "full_name": names.get(head_id)} if head_id and head_id != t.assignee_id else None,
            "ownership": [{"employee_id": r.employee_id, "full_name": names.get(r.employee_id), "note": r.note, "at": z(r.created_at)} for r in rows]}  # fmt: skip
