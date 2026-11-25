"""Relay: outbox events -> notifications (+ queued emails). Safe to run repeatedly and in parallel
(one pass at a time via scheduler.run_locked + unique keys), and it re-checks that scheduled reminders are still true before telling anyone."""

import logging
import re
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.modules.auth.models import User
from app.modules.notifications import resolver, templates
from app.modules.notifications.models import EmailLog, JobFailure, Notification, OutboxEvent, ReminderRule
from app.modules.org.models import Employee
from app.modules.tasks.models import TERMINAL, Task

log = logging.getLogger("tms.notifications")
MAX_ATTEMPTS = 5
# Events produced by the reminder scanner: they describe the deadline as it WAS when scheduled.
SCHEDULED = {"TASK_REMINDER_24H", "TASK_REMINDER_3H", "TASK_REMINDER_2H", "TASK_OVERDUE", "TASK_ESCALATION_1", "TASK_ESCALATION_2", "TASK_ESCALATION_3"}


def record_failure(db: Session, job: str, error: str, context: dict | None = None) -> None:
    db.add(JobFailure(job=job, error=error[:4000], context=context))


def still_valid(db: Session, event_type: str, task: Task | None, deadline_version: int | None) -> bool:
    """A reminder is only true if the task is still open, still on the same deadline, and still in a status that gets it.
    This is what stops an old schedule from ever firing after a deadline change, completion or cancellation."""
    if task is None or task.status in TERMINAL:
        return False
    if deadline_version is not None and task.deadline_version != deadline_version:
        return False
    rule_statuses = db.scalar(select(ReminderRule.statuses).where(ReminderRule.event_type == event_type))
    return rule_statuses is None or task.status in rule_statuses.split(",")


def _names(db: Session, user_ids: set[int | None]) -> dict[int, str]:
    ids = [u for u in user_ids if u]
    return dict(db.execute(select(Employee.user_id, Employee.full_name).where(Employee.user_id.in_(ids))).all()) if ids else {}


def _task_facts(db: Session, t: Task) -> dict:
    """Project, status, head, QA and everyone in the loop, for message emails."""
    from app.modules.tasks import loop
    from app.modules.tasks.models import Project

    name = lambda eid: (db.scalar(select(Employee.full_name).where(Employee.id == eid)) or "") if eid else ""  # noqa: E731
    return {"project": (db.scalar(select(Project.name).where(Project.id == t.project_id)) or "") if t.project_id else "", "status": t.status,
            "head": name(loop.head_id(db, t)), "qa": name(loop.qa_id(db, t)), "people": [name(i) for i in loop.loop_employee_ids(db, t)]}  # fmt: skip


def process_event(db: Session, ev: OutboxEvent) -> tuple[str, list[int]]:
    """Returns ('done' | 'skipped', user ids who got an in-app notification)."""
    task = db.get(Task, ev.task_id) if ev.task_id else None
    payload = ev.payload or {}
    if ev.event_type in SCHEDULED and not still_valid(db, ev.event_type, task, payload.get("deadline_version")):
        return "skipped", []
    recips = resolver.resolve(db, ev.event_type, task, ev.actor_user_id, payload)
    if not recips:
        return "done", []
    emp_names = {e.id: e.full_name for e in db.scalars(select(Employee).where(Employee.id.in_([x for x in (task.assignee_id, task.assigned_by_id) if x])))} if task else {}
    actor = _names(db, {ev.actor_user_id}).get(ev.actor_user_id) if ev.actor_user_id else None
    base = get_settings().app_base_url.rstrip("/")
    extra = _task_facts(db, task) if task else {}
    key = ev.dedupe_key or f"{ev.event_type}:{ev.id}"
    notified: list[int] = []
    for uid, r in recips.items():
        user = db.get(User, uid)
        c = SimpleNamespace(
            actor=actor, task_no=task.task_no if task else "", title=task.title if task else "", priority=task.priority if task else "",
            assignee=emp_names.get(task.assignee_id, "") if task else "", assigner=emp_names.get(task.assigned_by_id, "") if task else "",
            due=templates.when(task.due_at, user.timezone) if task else "", hours=round(task.estimated_seconds / 3600, 1) if task else "",
            due_after=templates.when(datetime.fromisoformat(str(payload.get("after", {}).get("due_at")).rstrip("Z")), user.timezone)
            if (payload.get("after") or {}).get("due_at") else "", a=payload.get("after") or {}, b=payload.get("before") or {},
            **extra,
        )  # fmt: skip
        title, body = templates.render(ev.event_type, c)
        pid = (payload.get("after") or {}).get("project_id")
        link = f"/tasks/{task.id}" if task else (f"/projects/{pid}" if pid else ("/employees" if ev.event_type == "EMPLOYEE_SIGNED_UP" else "/"))
        n = None
        if "in_app" in r.channels:
            try:
                with db.begin_nested():
                    n = Notification(user_id=uid, event_type=ev.event_type, title=title[:200], body=body, task_id=ev.task_id,
                                     reasons=sorted(r.reasons), dedupe_key=key, urgent=r.urgent)  # fmt: skip
                    db.add(n)
                    db.flush()
                notified.append(uid)
            except IntegrityError:  # already told: the unique key makes a duplicate impossible
                continue
        if "email" in r.channels:
            text, html = templates.email_bodies(title, body, base + link, r.urgent, "Open the task" if task else ("Open the project" if pid else "Open SeaWind"))
            db.add(EmailLog(notification_id=n.id if n else None, to_user_id=uid, to_email=user.email, subject=f"[SeaWind] {title}"[:255],
                            body_text=text, body_html=html, urgent=r.urgent, next_attempt_at=clock.utcnow()))  # fmt: skip
    return "done", notified


def relay_outbox(db: Session, limit: int = 200) -> list[int]:
    """Process pending events. Returns user ids to push a real-time signal to (the caller pushes AFTER commit)."""
    pushed: list[int] = []
    events = db.scalars(select(OutboxEvent).where(OutboxEvent.status == "pending").order_by(OutboxEvent.id).limit(limit).with_for_update()).all()
    for ev in events:
        try:
            with db.begin_nested():
                status, users = process_event(db, ev)
            ev.status, ev.processed_at = status, clock.utcnow()
            pushed += users
        except Exception as exc:  # noqa: BLE001 - one bad event must not block the others
            ev.attempts += 1
            ev.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            log.exception("outbox event %s failed", ev.id)
            if ev.attempts >= MAX_ATTEMPTS:
                ev.status, ev.processed_at = "failed", clock.utcnow()
                record_failure(db, "outbox_relay", ev.last_error, {"event_id": ev.id, "event_type": ev.event_type})
    db.flush()
    return pushed


# ------------------------------------------------------------------ reading and managing my notifications


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.is_read.is_(False))) or 0


def to_dict(n: Notification) -> dict:
    return {"id": n.id, "event_type": n.event_type, "title": n.title, "body": n.body, "task_id": n.task_id, "reasons": n.reasons or [],
            "urgent": n.urgent, "is_read": n.is_read, "created_at": n.created_at.isoformat() + "Z"}  # fmt: skip


def mark_all_read(db: Session, user_id: int) -> int:
    res = db.execute(update(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False)).values(is_read=True, read_at=clock.utcnow()))
    return res.rowcount or 0


def version_of(dedupe_key: str) -> int | None:
    m = re.search(r":v(\d+)", dedupe_key or "")
    return int(m.group(1)) if m else None
