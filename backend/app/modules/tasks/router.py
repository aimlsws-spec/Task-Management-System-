from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select

from app.core.deps import get_principal, require
from app.core.errors import AppError, NotFound
from app.core.schemas import Strict
from app.modules.rbac.policy import Principal
from app.modules.tasks import attachments as att
from app.modules.tasks import deadlines, delays, service, workflow
from app.modules.tasks.models import PRIORITIES, Project, Task, TaskAttachment, TaskCategory, TaskType
from app.modules.timetracking import service as ts

router = APIRouter(tags=["tasks"])
Priority = Literal["critical", "high", "medium", "low"]


class TaskIn(Strict):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=20000)
    instructions: str | None = Field(None, max_length=20000)
    assignee_id: int
    priority: Priority
    due_date: date
    start_date: date | None = None
    estimated_hours: float | None = Field(None, gt=0, le=1000)  # optional: owners give a deadline, not an effort estimate
    company_id: int | None = None
    project_id: int | None = None
    category_id: int | None = None
    type_id: int | None = None
    head_employee_id: int | None = None  # optional head who approves finished work; none = no head
    sub_head_employee_id: int | None = None  # optional sub-head
    qa_employee_id: int | None = None  # optional QA
    qa_employee_ids: list[int] | None = None  # optional multiple QA members


class TaskPatch(Strict):
    title: str | None = Field(None, min_length=3, max_length=200)
    description: str | None = Field(None, min_length=3, max_length=20000)
    instructions: str | None = Field(None, max_length=20000)
    start_date: date | None = None
    estimated_hours: float | None = Field(None, gt=0, le=1000)
    company_id: int | None = None
    project_id: int | None = None
    category_id: int | None = None
    type_id: int | None = None
    head_employee_id: int | None = None
    sub_head_employee_id: int | None = None
    qa_employee_id: int | None = None
    qa_employee_ids: list[int] | None = None


class ReassignIn(Strict):
    assignee_id: int
    reason: str | None = Field(None, max_length=1000)


class PriorityIn(Strict):
    priority: Priority
    reason: str | None = Field(None, max_length=1000)


class CancelIn(Strict):
    reason: str = Field(min_length=3, max_length=2000)


class StartIn(Strict):
    switch: bool = False  # stop the timer running on another task and start this one


class ReasonIn(Strict):
    reason: str = Field(min_length=3, max_length=2000)


class ProgressIn(Strict):
    progress_pct: int = Field(ge=0, le=100)
    note: str = Field(min_length=3, max_length=2000)


class FinishIn(Strict):
    """The employee's assurance when finishing work."""

    summary: str = Field(min_length=5, max_length=5000)
    tested: bool
    test_notes: str | None = Field(None, max_length=5000)
    evidence_url: str | None = Field(None, max_length=500)
    no_time_reason: str | None = Field(None, max_length=1000)  # only if no time was tracked on the task
    late_reason: str | None = Field(None, max_length=2000)  # one line, only when the task is overdue and unexplained


class ReviewIn(Strict):
    decision: Literal["approve", "reject"]
    reason_code: Literal["qa_defect", "incomplete", "requirement_change", "other"] | None = None
    comment: str | None = Field(None, max_length=2000)
    bug_sheet_url: str | None = Field(None, max_length=500)


class VerifyIn(Strict):
    note: str | None = Field(None, max_length=2000)


class RevertIn(Strict):
    reason_code: Literal["qa_defect", "incomplete", "requirement_change", "other"]
    reason: str = Field(min_length=5, max_length=2000)
    found_by: str | None = Field(None, max_length=60)  # e.g. "QA"
    bug_sheet_url: str | None = Field(None, max_length=500)


def _detail(p: Principal, t: Task) -> dict:
    d = service.task_dict(p.db, t, detail=True)
    d["allowed_actions"] = service.allowed_actions(p, t)
    d["timer_running"] = "pause" in d["allowed_actions"]
    d["status_history"] = service.status_history(p.db, t)
    d["time"] = ts.task_time(p.db, t)
    from app.modules.collab import blockers as blk

    d["blockers"] = [b | {"actions": blk.actions_for(p, t, p.db.get(blk.TaskBlocker, b["id"]))} for b in blk.list_for_task(p.db, p, t)]
    d["open_blockers"] = sum(1 for b in d["blockers"] if b["status"] in blk.OPEN_BLOCKER)
    st = delays.state_for(p.db, t)
    d["deadline"] = {"original_due_at": d["original_due_at"], "due_at": d["due_at"], "version": t.deadline_version,
                     "extension_count": t.extension_count, "history": deadlines.history(p.db, t),
                     "requests": deadlines.requests_for_task(p.db, t)}  # fmt: skip
    if delays.is_leadership(p) and not (p.employee and p.employee.id == t.assignee_id) and st["explanations"] and not st["released"]:
        st = st | {"awaiting_review": False, "latest_decision": None, "explanations": 0, "required": False, "why": None}  # not released yet
    d["delay"] = st | {"items": delays.explanations(p.db, t, p) if delays.can_see_explanations(p, t) else []}
    d |= workflow.detail_extras(p.db, t)
    d |= workflow.ownership_for(p.db, t)
    d["attachments"] = [_att(a) for a in p.db.scalars(select(TaskAttachment).where(TaskAttachment.task_id == t.id).order_by(TaskAttachment.id))]
    return d


def _att(a: TaskAttachment) -> dict:
    return {"id": a.id, "name": a.original_name, "size_bytes": a.size_bytes, "mime_type": a.mime_type, "at": service.z(a.created_at)}


# ---------------------------------------------------------------- tasks


@router.get("/tasks")
def list_tasks(
    status: str | None = None, priority: str | None = None, assignee_id: int | None = None,
    department_id: int | None = None, project_id: int | None = None, assigned_by_id: int | None = None,
    company_id: int | None = None,
    overdue: bool | None = None, open: bool | None = None, mine: bool | None = None, awaiting_my_review: bool | None = None,
    due_from: date | None = None, due_to: date | None = None, q: str | None = None,
    page: int = 1, page_size: int = 25, p: Principal = Depends(require("task.view")),
):  # fmt: skip
    f = dict(status=status, priority=priority, assignee_id=assignee_id, department_id=department_id, project_id=project_id,
             assigned_by_id=assigned_by_id, company_id=company_id, overdue=overdue, open=open, mine=mine, awaiting_my_review=awaiting_my_review, due_from=due_from, due_to=due_to, q=q)  # fmt: skip
    return service.list_tasks(p.db, p, f, max(1, page), max(1, min(page_size, 100)))


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, request: Request, p: Principal = Depends(require("task.create", "task.assign"))):
    t, warnings = service.create_task(p.db, p, body.model_dump(), request)
    return {"task": _detail(p, t), "warnings": warnings}


@router.get("/tasks/{task_id}")
def get_task(task_id: int, p: Principal = Depends(require("task.view"))):
    return _detail(p, service.get_visible_task(p.db, p, task_id))


@router.patch("/tasks/{task_id}")
def patch_task(task_id: int, body: TaskPatch, request: Request, p: Principal = Depends(require("task.view"))):
    t = service.get_visible_task(p.db, p, task_id)
    service.update_task(p.db, p, t, body.model_dump(exclude_unset=True), request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/reassign")
def reassign(task_id: int, body: ReassignIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = service.get_visible_task(p.db, p, task_id)
    service.reassign_task(p.db, p, t, body.assignee_id, body.reason, request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/priority")
def priority(task_id: int, body: PriorityIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = service.get_visible_task(p.db, p, task_id)
    service.change_priority(p.db, p, t, body.priority, body.reason, request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/cancel")
def cancel(task_id: int, body: CancelIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = service.get_visible_task(p.db, p, task_id)
    service.cancel_task(p.db, p, t, body.reason, request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/acknowledge")
def acknowledge(task_id: int, request: Request, p: Principal = Depends(require("task.view"))):
    t = service.get_visible_task(p.db, p, task_id)
    service.acknowledge_task(p.db, p, t, request)
    return _detail(p, t)


@router.get("/tasks/{task_id}/timeline")
def timeline(task_id: int, p: Principal = Depends(require("task.view"))):
    return service.timeline(p.db, service.get_visible_task(p.db, p, task_id))



# ---------------------------------------------------------------- the employee's work: timer, progress, finishing


def _task(p: Principal, task_id: int) -> Task:
    return service.get_visible_task(p.db, p, task_id)


@router.post("/tasks/{task_id}/start")
def start(task_id: int, request: Request, body: StartIn | None = None, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    ts.start_timer(p.db, p, t, bool(body and body.switch), request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/pause")
def pause(task_id: int, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    ts.stop_timer(p.db, p, t, "paused", request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/stop")
def stop(task_id: int, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    ts.stop_timer(p.db, p, t, "stopped", request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/hold")
def hold(task_id: int, body: ReasonIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    workflow.hold(p.db, p, t, body.reason, request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/unhold")
def unhold(task_id: int, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    workflow.unhold(p.db, p, t, request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/progress")
def progress(task_id: int, body: ProgressIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    workflow.add_progress(p.db, p, t, body.progress_pct, body.note, request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/complete")
def complete(task_id: int, body: FinishIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    workflow.complete(p.db, p, t, body.model_dump(), request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/submit-for-review")
def submit_for_review(task_id: int, body: FinishIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    workflow.submit_for_review(p.db, p, t, body.model_dump(), request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/review")
def review(task_id: int, body: ReviewIn, request: Request, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    if body.decision == "reject" and not (body.comment or "").strip():
        raise AppError("COMMENT_REQUIRED", "Say what needs to change", 422)
    workflow.review(p.db, p, t, body.decision == "approve", body.reason_code, body.comment, request, body.bug_sheet_url)
    return _detail(p, t)


@router.post("/tasks/{task_id}/verify")
def verify(task_id: int, request: Request, body: VerifyIn | None = None, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    workflow.verify(p.db, p, t, body.note if body else None, request)
    return _detail(p, t)


@router.post("/tasks/{task_id}/revert")
def revert(task_id: int, body: RevertIn, request: Request, p: Principal = Depends(require("task.view"))):
    """Send finished work back, e.g. QA found the feature not working. Allowed any time after completion."""
    t = _task(p, task_id)
    workflow.revert(p.db, p, t, body.reason_code, body.reason, body.found_by, request, body.bug_sheet_url)
    return _detail(p, t)


class OwnershipIn(Strict):
    note: str | None = Field(None, max_length=1000)


@router.post("/tasks/{task_id}/take-ownership")
def take_ownership(task_id: int, request: Request, body: OwnershipIn | None = None, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    workflow.take_ownership(p.db, p, t, body.note if body else None, request)
    return _detail(p, t)


@router.get("/tasks/{task_id}/time")
def task_time(task_id: int, p: Principal = Depends(require("task.view"))):
    return ts.task_time(p.db, _task(p, task_id))


# ---------------------------------------------------------------- who has how much work


@router.get("/workload")
def workload(p: Principal = Depends(require("task.assign"))):
    """People you can assign to, with their current load. Powers the assignee picker and the workload view."""
    return service.workload(p.db, p)


# ---------------------------------------------------------------- attachments


@router.post("/tasks/{task_id}/attachments", status_code=201)
async def upload(task_id: int, request: Request, file: UploadFile = File(...), p: Principal = Depends(require("task.view"))):
    t = service.get_visible_task(p.db, p, task_id)
    return _att(await att.save_upload(p.db, p, t, file, request))


@router.get("/attachments/{att_id}/download")
def download(att_id: int, p: Principal = Depends(require("task.view"))):
    a = p.db.get(TaskAttachment, att_id)
    if a is None:
        raise NotFound("Attachment")
    service.get_visible_task(p.db, p, a.task_id)  # re-check task visibility on EVERY download
    path = att.path_for(a.stored_key)
    if not path.exists():
        raise NotFound("Attachment")
    return FileResponse(path, media_type=a.mime_type, filename=a.original_name, content_disposition_type="attachment")


# ---------------------------------------------------------------- projects + form metadata


@router.get("/task-meta")
def task_meta(p: Principal = Depends(get_principal)):
    """Everything the create-task form needs besides the people list (which comes from /workload)."""
    db = p.db
    return {
        "priorities": list(PRIORITIES),
        "categories": [{"id": c.id, "name": c.name} for c in db.scalars(select(TaskCategory).where(TaskCategory.is_active.is_(True)).order_by(TaskCategory.name))],
        "types": [{"id": t.id, "name": t.name, "requires_review": t.requires_review} for t in db.scalars(select(TaskType).where(TaskType.is_active.is_(True)).order_by(TaskType.name))],
        "projects": [{"id": x.id, "code": x.code, "name": x.name} for x in db.scalars(select(Project).where(Project.status == "active").order_by(Project.name))],
    }

