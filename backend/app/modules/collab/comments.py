"""The task discussion: comments, questions, clarifications, replies, @mentions. Nothing is ever deleted; an author can
correct their own comment for ten minutes and the original text stays in the audit trail."""

from datetime import timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError, Forbidden, NotFound
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.collab.models import CommentMention, TaskComment
from app.modules.notifications import resolver
from app.modules.org.models import Department, Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import loop
from app.modules.tasks.models import Task, TaskAttachment
from app.modules.tasks.service import z

EDIT_WINDOW = timedelta(minutes=10)
KINDS = ("comment", "question", "clarification")


def can_discuss(p: Principal, t: Task) -> bool:
    """Same people who can see the task's work: the assignee, their management chain, and whoever assigned it."""
    me = p.employee.id if p.employee else -1
    in_loop = me in (loop.head_id(p.db, t), loop.qa_id(p.db, t))  # the head and QA (task's own or project's) take part
    return p.has("comment.create") and (t.assignee_id == me or t.assigned_by_id == me or in_loop or p.can_see("task.view", t.assignee_id))


def mentionable(db: Session, t: Task) -> list[dict]:
    """People a comment on this task may @mention: those with a stake in it. Nobody else is ever pinged."""
    out: dict[int, dict] = {}

    def add(emp_id: int | None, why: str) -> None:
        e = db.get(Employee, emp_id) if emp_id else None
        if e is not None and e.status != "inactive" and e.user_id not in out and db.get(User, e.user_id).is_active:
            out[e.user_id] = {"user_id": e.user_id, "full_name": e.full_name, "job_title": e.job_title, "why": why}

    add(t.assignee_id, "Assignee")
    add(t.assigned_by_id, "Assigned the task")
    add(loop.head_id(db, t), "Head")
    add(loop.qa_id(db, t), "QA")
    for emp in resolver.manager_chain(db, t.assignee_id):
        add(emp, "In the reporting line")
    add(db.scalar(select(Department.head_employee_id).where(Department.id == t.department_id)), "Department head")
    for code in ("ceo", "owner"):
        for uid in resolver._users_with_role(db, code):  # noqa: SLF001
            e = db.scalar(select(Employee).where(Employee.user_id == uid))
            add(e.id if e else None, code.upper())
    return sorted(out.values(), key=lambda x: x["full_name"])


def _check_attachment(db: Session, p: Principal, t: Task, attachment_id: int | None) -> None:
    if attachment_id is None:
        return
    a = db.get(TaskAttachment, attachment_id)
    if a is None or a.task_id != t.id or a.uploaded_by_user_id != p.user.id:
        raise AppError("INVALID_ATTACHMENT", "Attach the file to this task first, then reference it", 422)


def add_comment(db: Session, p: Principal, t: Task, kind: str, body: str, parent_id: int | None, mentions: list[int],
                attachment_id: int | None, request: Request) -> TaskComment:  # fmt: skip
    if not can_discuss(p, t):
        raise Forbidden()
    body = (body or "").strip()
    if not body:
        raise AppError("BODY_REQUIRED", "Write something first", 422)
    if kind not in KINDS:
        raise AppError("INVALID_KIND", "Kind must be comment, question or clarification", 422)
    parent = None
    if parent_id is not None:
        parent = db.get(TaskComment, parent_id)
        if parent is None or parent.task_id != t.id:
            raise AppError("INVALID_PARENT", "That comment is not part of this task", 422)
        kind = "reply"
    allowed = {m["user_id"] for m in mentionable(db, t)} - {p.user.id}
    unknown = [m for m in mentions if m not in allowed]
    if unknown:
        raise AppError("INVALID_MENTION", "You can only mention people involved in this task", 422)
    _check_attachment(db, p, t, attachment_id)
    c = TaskComment(task_id=t.id, author_user_id=p.user.id, parent_id=parent_id, kind=kind, body=body, attachment_id=attachment_id)
    db.add(c)
    db.flush()
    for uid in sorted(set(mentions)):
        db.add(CommentMention(comment_id=c.id, user_id=uid))
    db.flush()
    action = "QUESTION_ASKED" if kind in ("question", "clarification") else "COMMENT_ADDED"
    audit.log(db, p.user.id, action, "task", t.id, after={"comment_id": c.id, "kind": kind, "body": body, "mentions": sorted(set(mentions)),
                                                        "author_user_id": p.user.id, "parent_author_user_id": parent.author_user_id if parent else None},
              request=request, task_id=t.id)  # fmt: skip
    return c


def edit_comment(db: Session, p: Principal, c: TaskComment, body: str, request: Request) -> TaskComment:
    t = db.get(Task, c.task_id)
    if not can_discuss(p, t):
        raise NotFound("Comment")
    if c.author_user_id != p.user.id:
        raise Forbidden("You can only edit your own comments")
    if clock.utcnow() - c.created_at > EDIT_WINDOW:
        raise AppError("EDIT_WINDOW_CLOSED", "Comments can only be corrected for 10 minutes. Add a new comment instead.", 409)
    body = (body or "").strip()
    if not body:
        raise AppError("BODY_REQUIRED", "A comment cannot be empty", 422)
    before = c.body
    c.body, c.edited_at = body, clock.utcnow()
    audit.log(db, p.user.id, "COMMENT_EDITED", "task", t.id, before={"comment_id": c.id, "body": before}, after={"comment_id": c.id, "body": body}, request=request, task_id=t.id)
    return c


def list_comments(db: Session, t: Task) -> list[dict]:
    names = dict(db.execute(select(Employee.user_id, Employee.full_name)).all())
    rows = db.scalars(select(TaskComment).where(TaskComment.task_id == t.id).order_by(TaskComment.id)).all()
    ments: dict[int, list[int]] = {}
    for m in db.scalars(select(CommentMention).where(CommentMention.comment_id.in_([c.id for c in rows]))) if rows else []:
        ments.setdefault(m.comment_id, []).append(m.user_id)
    files = {a.id: a.original_name for a in db.scalars(select(TaskAttachment).where(TaskAttachment.id.in_([c.attachment_id for c in rows if c.attachment_id])))} if rows else {}
    return [
        {"id": c.id, "parent_id": c.parent_id, "kind": c.kind, "body": c.body, "author": names.get(c.author_user_id), "author_user_id": c.author_user_id,
         "mentions": [{"user_id": u, "full_name": names.get(u)} for u in ments.get(c.id, [])], "attachment": {"id": c.attachment_id, "name": files.get(c.attachment_id)} if c.attachment_id else None,
         "edited": c.edited_at is not None, "at": z(c.created_at)}
        for c in rows
    ]  # fmt: skip
