from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.core.deps import require
from app.core.errors import NotFound
from app.core.schemas import Strict
from app.modules.collab import blockers, comments
from app.modules.collab.models import TaskBlocker, TaskComment
from app.modules.rbac.policy import Principal
from app.modules.tasks import service
from app.modules.tasks.models import Task

router = APIRouter(tags=["blockers and comments"])
BType = Literal["technical", "dependency", "information", "resource", "access", "other"]


class BlockerIn(Strict):
    blocker_type: BType
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=5000)
    impact: str | None = Field(None, max_length=2000)
    blocks_work: bool = True  # False = an issue to flag, but work can continue
    expected_resolution: str | None = Field(None, max_length=2000)
    attachment_id: int | None = None


class NoteIn(Strict):
    note: str = Field(min_length=2, max_length=2000)


class OptionalNoteIn(Strict):
    note: str | None = Field(None, max_length=2000)


class AssignIn(Strict):
    owner_employee_id: int
    note: str | None = Field(None, max_length=2000)


class CommentIn(Strict):
    kind: Literal["comment", "question", "clarification"] = "comment"
    body: str = Field(min_length=1, max_length=5000)
    parent_id: int | None = None
    mentions: list[int] = Field(default_factory=list, max_length=20)
    attachment_id: int | None = None


class CommentEdit(Strict):
    body: str = Field(min_length=1, max_length=5000)


def _task(p: Principal, task_id: int) -> Task:
    return service.get_visible_task(p.db, p, task_id)


def _out(p: Principal, b: TaskBlocker) -> dict:
    t = p.db.get(Task, b.task_id)
    return blockers.blocker_dict(p.db, b, True) | {"actions": blockers.actions_for(p, t, b)}


# ---------------------------------------------------------------- blockers


@router.post("/tasks/{task_id}/blockers", status_code=201)
def raise_blocker(task_id: int, body: BlockerIn, request: Request, p: Principal = Depends(require("blocker.raise"))):
    b = blockers.raise_blocker(p.db, p, _task(p, task_id), body.model_dump(), request)
    return _out(p, b)


@router.get("/tasks/{task_id}/blockers")
def task_blockers(task_id: int, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    return [d | {"actions": blockers.actions_for(p, t, p.db.get(TaskBlocker, d["id"]))} for d in blockers.list_for_task(p.db, p, t)]


@router.get("/blockers")
def blocker_queue(status: str | None = None, open: bool = True, page: int = 1, page_size: int = 50, p: Principal = Depends(require("blocker.view"))):
    """Blockers in your scope (employees: their own). Open ones by default."""
    return blockers.queue(p.db, p, status, open, max(1, page), max(1, min(page_size, 100)))


@router.get("/blockers/{blocker_id}")
def blocker_detail(blocker_id: int, p: Principal = Depends(require("task.view"))):
    b, _t = blockers._load(p.db, p, blocker_id)  # noqa: SLF001
    return _out(p, b)


@router.post("/blockers/{blocker_id}/acknowledge")
def acknowledge(blocker_id: int, request: Request, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.acknowledge(p.db, p, blocker_id, request))


@router.post("/blockers/{blocker_id}/assign")
def assign(blocker_id: int, body: AssignIn, request: Request, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.assign(p.db, p, blocker_id, body.owner_employee_id, body.note, request))


@router.post("/blockers/{blocker_id}/start")
def start(blocker_id: int, request: Request, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.start(p.db, p, blocker_id, request))


@router.post("/blockers/{blocker_id}/reply")
def reply(blocker_id: int, body: NoteIn, request: Request, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.reply(p.db, p, blocker_id, body.note, request))


@router.post("/blockers/{blocker_id}/resolve")
def resolve(blocker_id: int, body: NoteIn, request: Request, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.resolve(p.db, p, blocker_id, body.note, request))


@router.post("/blockers/{blocker_id}/close")
def close(blocker_id: int, request: Request, body: OptionalNoteIn | None = None, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.close(p.db, p, blocker_id, body.note if body else None, request))


@router.post("/blockers/{blocker_id}/reopen")
def reopen(blocker_id: int, body: NoteIn, request: Request, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.reopen(p.db, p, blocker_id, body.note, request))


@router.post("/blockers/{blocker_id}/escalate")
def escalate(blocker_id: int, body: NoteIn, request: Request, p: Principal = Depends(require("task.view"))):
    return _out(p, blockers.escalate(p.db, p, blocker_id, body.note, request))


# ---------------------------------------------------------------- comments and questions


@router.get("/tasks/{task_id}/comments")
def list_comments(task_id: int, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    return comments.list_comments(p.db, t) if comments.can_discuss(p, t) else []


@router.get("/tasks/{task_id}/mentionable")
def mentionable(task_id: int, p: Principal = Depends(require("task.view"))):
    t = _task(p, task_id)
    return [m for m in comments.mentionable(p.db, t) if m["user_id"] != p.user.id] if comments.can_discuss(p, t) else []


@router.post("/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: int, body: CommentIn, request: Request, p: Principal = Depends(require("comment.create"))):
    t = _task(p, task_id)
    c = comments.add_comment(p.db, p, t, body.kind, body.body, body.parent_id, body.mentions, body.attachment_id, request)
    return next(x for x in comments.list_comments(p.db, t) if x["id"] == c.id)


@router.patch("/comments/{comment_id}")
def edit_comment(comment_id: int, body: CommentEdit, request: Request, p: Principal = Depends(require("comment.create"))):
    c = p.db.get(TaskComment, comment_id)
    if c is None:
        raise NotFound("Comment")
    t = service.get_visible_task(p.db, p, c.task_id)
    comments.edit_comment(p.db, p, c, body.body, request)
    return next(x for x in comments.list_comments(p.db, t) if x["id"] == c.id)
