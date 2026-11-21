from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import func, select

from app.core import clock
from app.core.deps import get_principal, require
from app.core.errors import AppError, NotFound
from app.core.schemas import Strict
from app.modules.audit import service as audit
from app.modules.audit.models import SystemSetting
from app.modules.notifications import service, templates
from app.modules.notifications.models import (
    EmailLog,
    JobFailure,
    Notification,
    NotificationPreference,
    NotificationRule,
    OutboxEvent,
    ReminderRule,
)
from app.modules.rbac.policy import Principal

router = APIRouter(tags=["notifications"])
SCHEDULER_STALE_SECONDS = 180  # no pass for 3 minutes = the cron job is not running


# ---------------------------------------------------------------- my notifications


@router.get("/notifications")
def my_notifications(unread: bool = False, page: int = 1, page_size: int = 30, p: Principal = Depends(get_principal)):
    stmt = select(Notification).where(Notification.user_id == p.user.id)
    if unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    total = p.db.scalar(select(func.count()).select_from(stmt.subquery()))
    page_size = max(1, min(page_size, 100))
    rows = p.db.scalars(stmt.order_by(Notification.id.desc()).offset((max(1, page) - 1) * page_size).limit(page_size)).all()
    return {"items": [service.to_dict(n) for n in rows], "total": total, "unread": service.unread_count(p.db, p.user.id)}


@router.get("/notifications/unread-count")
def unread_count(p: Principal = Depends(get_principal)):
    return {"unread": service.unread_count(p.db, p.user.id)}


@router.put("/notifications/{nid}/read")
def mark_read(nid: int, p: Principal = Depends(get_principal)):
    n = p.db.get(Notification, nid)
    if n is None or n.user_id != p.user.id:
        raise NotFound("Notification")  # nobody can read or touch someone else's
    if not n.is_read:
        n.is_read, n.read_at = True, clock.utcnow()
    return service.to_dict(n)


@router.post("/notifications/read-all")
def read_all(p: Principal = Depends(get_principal)):
    return {"marked": service.mark_all_read(p.db, p.user.id)}


# ---------------------------------------------------------------- preferences (mandatory notices cannot be muted)


class PrefIn(Strict):
    event_type: str = Field(max_length=60)
    channel: Literal["in_app", "email"]
    enabled: bool


@router.get("/me/notification-preferences")
def my_preferences(p: Principal = Depends(get_principal)):
    rules = p.db.scalars(select(NotificationRule).where(NotificationRule.enabled.is_(True))).all()
    by_event: dict[str, list[NotificationRule]] = {}
    for r in rules:
        by_event.setdefault(r.event_type, []).append(r)
    muted = {(x.event_type, x.channel) for x in p.db.scalars(select(NotificationPreference).where(NotificationPreference.user_id == p.user.id, NotificationPreference.enabled.is_(False)))}
    out = []
    for event, rs in sorted(by_event.items(), key=lambda kv: templates.EVENT_LABELS.get(kv[0], kv[0])):
        channels = sorted({c.strip() for r in rs for c in r.channels.split(",")})
        out.append({
            "event_type": event, "label": templates.EVENT_LABELS.get(event, event), "channels": channels,
            "locked": all(r.mandatory for r in rs),  # every reason to be told is mandatory: nothing to mute
            "in_app": ("in_app" in channels) and (event, "in_app") not in muted,
            "email": ("email" in channels) and (event, "email") not in muted,
        })  # fmt: skip
    return out


@router.put("/me/notification-preferences")
def set_preference(body: PrefIn, p: Principal = Depends(get_principal)):
    row = p.db.get(NotificationPreference, (p.user.id, body.event_type, body.channel))
    if row is None:
        p.db.add(NotificationPreference(user_id=p.user.id, event_type=body.event_type, channel=body.channel, enabled=body.enabled))
    else:
        row.enabled = body.enabled
    return {"event_type": body.event_type, "channel": body.channel, "enabled": body.enabled}


# ---------------------------------------------------------------- Admin: rules, reminder timing, email log, jobs


class RuleEdit(Strict):
    enabled: bool | None = None
    channels: Literal["in_app", "email", "in_app,email"] | None = None
    mandatory: bool | None = None
    urgent: bool | None = None


class ReminderEdit(Strict):
    enabled: bool | None = None
    minutes: int | None = Field(None, ge=0, le=10080)
    working_days: int | None = Field(None, ge=0, le=60)


def _rule(r: NotificationRule) -> dict:
    return {"id": r.id, "event_type": r.event_type, "label": templates.EVENT_LABELS.get(r.event_type, r.event_type), "selector": r.selector,
            "channels": r.channels, "mandatory": r.mandatory, "urgent": r.urgent, "enabled": r.enabled, "condition": r.condition_json}  # fmt: skip


@router.get("/admin/notification-rules")
def list_rules(p: Principal = Depends(require("notification.rules.manage"))):
    return [_rule(r) for r in p.db.scalars(select(NotificationRule).order_by(NotificationRule.event_type, NotificationRule.id))]


@router.patch("/admin/notification-rules/{rid}")
def edit_rule(rid: int, body: RuleEdit, request: Request, p: Principal = Depends(require("notification.rules.manage"))):
    r = p.db.get(NotificationRule, rid)
    if r is None:
        raise NotFound("Rule")
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(r, k) for k in data}
    for k, v in data.items():
        setattr(r, k, v)
    audit.log(p.db, p.user.id, "NOTIFICATION_RULE_CHANGED", "notification_rule", r.id, before=before, after=data, request=request)
    return _rule(r)


@router.get("/admin/reminder-rules")
def list_reminders(p: Principal = Depends(require("notification.rules.manage"))):
    return [{"id": r.id, "code": r.code, "kind": r.kind, "minutes": r.minutes, "working_days": r.working_days, "event_type": r.event_type,
             "statuses": r.statuses.split(","), "enabled": r.enabled} for r in p.db.scalars(select(ReminderRule).order_by(ReminderRule.sort_order))]  # fmt: skip


@router.patch("/admin/reminder-rules/{rid}")
def edit_reminder(rid: int, body: ReminderEdit, request: Request, p: Principal = Depends(require("notification.rules.manage"))):
    r = p.db.get(ReminderRule, rid)
    if r is None:
        raise NotFound("Reminder rule")
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(r, k) for k in data}
    for k, v in data.items():
        setattr(r, k, v)
    audit.log(p.db, p.user.id, "REMINDER_RULE_CHANGED", "reminder_rule", r.id, before=before, after=data, request=request)
    return {"id": r.id, "code": r.code, "minutes": r.minutes, "working_days": r.working_days, "enabled": r.enabled}


@router.get("/admin/email-logs")
def email_logs(status: str | None = None, page: int = 1, page_size: int = 50, p: Principal = Depends(require("notification.rules.manage"))):
    stmt = select(EmailLog)
    if status:
        stmt = stmt.where(EmailLog.status == status)
    total = p.db.scalar(select(func.count()).select_from(stmt.subquery()))
    page_size = max(1, min(page_size, 200))
    rows = p.db.scalars(stmt.order_by(EmailLog.id.desc()).offset((max(1, page) - 1) * page_size).limit(page_size)).all()
    items = [{"id": e.id, "to": e.to_email, "subject": e.subject, "status": e.status, "attempts": e.attempts, "urgent": e.urgent, "error": e.last_error,
              "backend": e.backend, "created_at": e.created_at.isoformat() + "Z", "sent_at": e.sent_at.isoformat() + "Z" if e.sent_at else None,
              "next_attempt_at": e.next_attempt_at.isoformat() + "Z"} for e in rows]  # fmt: skip
    return {"items": items, "total": total}


@router.post("/admin/email-logs/{eid}/retry")
def retry_email(eid: int, request: Request, p: Principal = Depends(require("notification.rules.manage"))):
    e = p.db.get(EmailLog, eid)
    if e is None:
        raise NotFound("Email")
    e.status, e.attempts, e.next_attempt_at, e.last_error = "queued", 0, clock.utcnow(), None
    audit.log(p.db, p.user.id, "EMAIL_RETRY_REQUESTED", "email_log", e.id, request=request)
    return {"id": e.id, "status": e.status}


@router.get("/admin/jobs/failures")
def job_failures(p: Principal = Depends(require("notification.rules.manage"))):
    rows = p.db.scalars(select(JobFailure).order_by(JobFailure.id.desc()).limit(100)).all()
    return [{"id": f.id, "job": f.job, "error": f.error, "context": f.context, "created_at": f.created_at.isoformat() + "Z"} for f in rows]


@router.get("/admin/jobs/status")
def job_status(p: Principal = Depends(require("notification.rules.manage"))):
    from app.core.config import get_settings

    s = get_settings()
    st = p.db.get(SystemSetting, "scheduler_status")
    last = st.value.get("last_tick_at") if st and isinstance(st.value, dict) else None
    age = int((clock.utcnow() - datetime.fromisoformat(last.removesuffix("Z"))).total_seconds()) if last else None
    count = lambda stmt: p.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0  # noqa: E731
    return {
        "scheduler": st.value if st else None, "scheduler_age_seconds": age,
        "scheduler_running": age is not None and age <= SCHEDULER_STALE_SECONDS,  # the cron job runs every minute
        "email_backend": s.email_backend,
        "smtp_configured": bool(s.smtp_host), "app_base_url": s.app_base_url,
        "email_links_are_local": any(h in s.app_base_url for h in ("localhost", "127.0.0.1", "0.0.0.0")), "pending_events": count(select(OutboxEvent).where(OutboxEvent.status == "pending")),
        "queued_emails": count(select(EmailLog).where(EmailLog.status == "queued")),
        "failed_emails": count(select(EmailLog).where(EmailLog.status == "failed")),
        "failed_events": count(select(OutboxEvent).where(OutboxEvent.status == "failed")),
    }  # fmt: skip


@router.post("/admin/jobs/run-now")
def run_now(request: Request, p: Principal = Depends(require("notification.rules.manage"))):
    """Run one full background pass immediately (reminder scan, notifications, email). It takes the same lock as the cron
    job, so it can never overlap a cron run: if one is running right now this answers 409 and does nothing."""
    from app.core.db import SessionLocal
    from app.jobs.scheduler import run_locked

    p.db.commit()  # make sure everything the caller just did is visible to the job's own session
    result = run_locked(SessionLocal)
    if result is None:
        raise AppError("SCHEDULER_BUSY", "A background pass is already running (the cron job). Try again in a moment.", 409)
    audit.log(p.db, p.user.id, "JOBS_RUN_NOW", "jobs", "scheduler", after={k: v for k, v in result.items() if k != "emails"}, request=request)
    return result
