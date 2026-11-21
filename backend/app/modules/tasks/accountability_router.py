"""Deadlines, extension requests, delay explanations and the manager review queue."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.core.deps import require
from app.core.errors import NotFound
from app.core.schemas import Strict
from app.modules.rbac.policy import Principal
from app.modules.tasks import deadlines, delays, service
from app.modules.tasks.models import DelayReason, ExtensionRequest, Task
from app.modules.tasks.router import _detail

router = APIRouter(tags=["deadlines and delays"])


class DeadlineIn(Strict):
    due_date: date
    reason: str = Field(min_length=10, max_length=2000)


class ExtensionIn(DeadlineIn):
    pass


class ExtensionDecisionIn(Strict):
    decision: Literal["approve", "reject"]
    note: str | None = Field(None, max_length=2000)
    due_date: date | None = None  # approve for a different date than requested


class DelayIn(Strict):
    reason: str = Field(min_length=5, max_length=5000)
    progress_pct: int = Field(ge=0, le=100)
    work_completed: str = Field(min_length=5, max_length=5000)
    remaining_work: str = Field(min_length=3, max_length=5000)
    blockers: str | None = Field(None, max_length=5000)
    expected_date: date
    attachment_id: int | None = None


class DelayReviewIn(Strict):
    decision: Literal["accepted", "clarification_requested", "rejected", "revised_deadline_approved", "escalated"]
    comment: str | None = Field(None, max_length=2000)
    due_date: date | None = None  # for revised_deadline_approved


def _task(p: Principal, task_id: int) -> Task:
    return service.get_visible_task(p.db, p, task_id)


# ---------------------------------------------------------------- deadlines


@router.post("/tasks/{task_id}/deadline")
def change_deadline(task_id: int, body: DeadlineIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    _hist, warnings = deadlines.change_deadline(p.db, p, t, body.due_date, body.reason, request)
    return {"task": _detail(p, t), "warnings": warnings}


@router.get("/tasks/{task_id}/deadline-history")
def deadline_history(task_id: int, p: Principal = Depends(require("task.view"))):
    return deadlines.history(p.db, _task(p, task_id))


@router.post("/tasks/{task_id}/extension-requests", status_code=201)
def request_extension(task_id: int, body: ExtensionIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    return deadlines.request_dict(p.db, deadlines.request_extension(p.db, p, t, body.due_date, body.reason, request))


@router.get("/extension-requests")
def extension_queue(p: Principal = Depends(require("task.deadline.edit"))):
    """Pending requests you can decide."""
    return deadlines.pending_queue(p.db, p)


@router.post("/extension-requests/{request_id}/decision")
def decide_extension(request_id: int, body: ExtensionDecisionIn, request: Request, p: Principal = Depends(require("task.deadline.edit"))):
    er = p.db.get(ExtensionRequest, request_id)
    if er is None:
        raise NotFound("Request")
    er, warnings = deadlines.decide_extension(p.db, p, er, body.decision == "approve", body.note, body.due_date, request)
    return {"request": deadlines.request_dict(p.db, er), "warnings": warnings}


@router.get("/stats/deadlines")
def deadline_stats(p: Principal = Depends(require("task.view"))):
    """How often deadlines move, and for whom, within your scope."""
    return deadlines.stats(p.db, p)


# ---------------------------------------------------------------- delay explanations


@router.post("/tasks/{task_id}/delay-reasons", status_code=201)
def submit_explanation(task_id: int, body: DelayIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    delays.submit(p.db, p, t, body.model_dump(), request)
    return _detail(p, t)


@router.get("/tasks/{task_id}/delay-reasons")
def list_explanations(task_id: int, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    if not delays.can_see_explanations(p, t):
        raise NotFound("Task")
    return delays.explanations(p.db, t, p)


@router.post("/delay-reasons/{reason_id}/review")
def review_explanation(reason_id: int, body: DelayReviewIn, request: Request, p: Principal = Depends(require("delay.review"))):
    r = p.db.get(DelayReason, reason_id)
    if r is None:
        raise NotFound("Explanation")
    _row, warnings = delays.review(p.db, p, r, body.decision, body.comment, body.due_date, request)
    return {"task": _detail(p, p.db.get(Task, r.task_id)), "warnings": warnings}


@router.get("/delays/queue")
def delay_queue(p: Principal = Depends(require("delay.review"))):
    """Overdue tasks with no valid explanation, and explanations waiting for your decision."""
    return delays.queue(p.db, p)
