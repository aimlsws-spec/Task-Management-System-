"""Deadline reminders, overdue notices and working-day escalations.

SCAN-based, not pre-scheduled: every run looks at the tasks as they are NOW, so nothing is ever left to cancel when a
deadline changes or a task is finished. Exactly-once comes from a unique row (task + rule + deadline version +
assignee) written BEFORE the event; a second run, or a parallel one, finds the row and does nothing."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.grace import late_after
from app.modules.notifications.models import ReminderLog, ReminderRule
from app.modules.notifications.outbox import emit
from app.modules.tasks.models import TERMINAL, Task, TaskDeadlineHistory
from app.modules.workcal import service as cal

HORIZON_DAYS = 120  # ignore tasks overdue for longer than this (they were escalated long ago)


def _fire(db: Session, t: Task, rule: ReminderRule, now: datetime) -> bool:
    try:
        with db.begin_nested():
            db.add(ReminderLog(task_id=t.id, rule_id=rule.id, deadline_version=t.deadline_version, assignee_id=t.assignee_id, fired_at=now))
            db.flush()
    except IntegrityError:
        return False  # already sent for this deadline: exactly-once
    emit(db, rule.event_type, task_id=t.id, actor_user_id=None,
         payload={"deadline_version": t.deadline_version, "rule": rule.code, "due_at": t.due_at.isoformat() + "Z"},
         dedupe_key=f"{rule.event_type}:{t.id}:v{t.deadline_version}:{t.assignee_id}")  # fmt: skip
    return True


def scan(db: Session, now: datetime | None = None) -> dict:
    now = now or clock.utcnow()
    fired: dict[str, int] = {}
    rules = db.scalars(select(ReminderRule).where(ReminderRule.enabled.is_(True)).order_by(ReminderRule.sort_order)).all()
    if not rules:
        return fired
    soonest = now + timedelta(minutes=max((r.minutes for r in rules if r.kind == "before"), default=0))
    tasks = db.scalars(
        select(Task).where(Task.status.notin_(TERMINAL), Task.due_at <= soonest, Task.due_at >= now - timedelta(days=HORIZON_DAYS)).order_by(Task.id)
    ).all()
    if not tasks:
        return fired
    # When did each task's CURRENT deadline begin? A reminder moment before that is not sent ("24 h before" is
    # meaningless for a task that was only given 3 hours, or for a deadline that was just moved).
    begins = {
        (h.task_id, h.deadline_version): h.created_at
        for h in db.scalars(select(TaskDeadlineHistory).where(TaskDeadlineHistory.task_id.in_([t.id for t in tasks])))
    }
    for t in tasks:
        started = begins.get((t.id, t.deadline_version), t.assigned_at)
        for rule in rules:
            if t.status not in rule.statuses.split(","):
                continue  # on hold / under review / finished: no reminders
            if rule.kind == "before":
                moment = t.due_at - timedelta(minutes=rule.minutes)
                due_now = moment <= now < t.due_at and moment >= started
            elif rule.kind == "at_due":
                due_now = late_after(t.due_at) <= now  # "overdue" starts after the grace period
            else:  # after N working days (Sundays, off Saturdays and holidays do not count)
                local = cal.utc_to_local(db, t.due_at)
                moment = cal.local_to_utc(db, datetime.combine(cal.add_working_days(db, local.date(), rule.working_days), local.time()))
                due_now = late_after(t.due_at) < now and moment <= now
            if due_now and _fire(db, t, rule, now):
                fired[rule.code] = fired.get(rule.code, 0) + 1
    db.flush()
    return fired
