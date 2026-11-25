"""Sending email: pluggable backend, retries with backoff, and a working-hours window for non-urgent mail.

Failures never block anything else: an in-app notification already exists whatever happens to its email."""

import logging
import smtplib
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.modules.notifications.models import EmailLog, Notification
from app.modules.notifications.service import MAX_ATTEMPTS, SCHEDULED, record_failure, still_valid, version_of
from app.modules.tasks.models import Task
from app.modules.workcal import service as cal

log = logging.getLogger("tms.mail")
BACKOFF_SECONDS = (60, 300, 1800, 7200, 43200)  # 1 min, 5 min, 30 min, 2 h, 12 h
PERMANENT = (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError)
# Addresses that can never receive mail (reserved for documentation/testing). The demo accounts use them.
RESERVED_DOMAINS = {"example.com", "example.org", "example.net"}
RESERVED_SUFFIXES = (".local", ".test", ".invalid", ".localhost", ".example")


def is_reserved_recipient(address: str) -> bool:
    dom = address.rsplit("@", 1)[-1].strip().lower()
    return dom in RESERVED_DOMAINS or any(dom.endswith("." + d) for d in RESERVED_DOMAINS) or dom.endswith(RESERVED_SUFFIXES)


def real_mail_server() -> bool:
    """True when mail would leave this machine (a local test SMTP server on loopback does not count)."""
    s = get_settings()
    return s.email_backend == "smtp" and s.smtp_host not in ("", "127.0.0.1", "localhost", "::1")


# Emails people act on must not wait for the next working day: assigned, reminders, overdue, delay reasons, new sign-ups.
IMMEDIATE_EVENTS = {
    "TASK_CREATED", "TASK_REASSIGNED", "TASK_REMINDER_24H", "TASK_REMINDER_3H", "TASK_REMINDER_2H", "TASK_OVERDUE",
    "TASK_ESCALATION_1", "TASK_ESCALATION_2", "TASK_ESCALATION_3",
    "DELAY_EXPLANATION_SUBMITTED", "DELAY_REVIEWED", "DELAY_RELEASED", "EXTENSION_DECIDED", "EMPLOYEE_SIGNED_UP",
    "PROJECT_HEAD_NAMED", "PROJECT_TASK_ASSIGNED", "TASK_HEAD_REVIEW_NEEDED", "TASK_HEAD_APPROVED", "TASK_LEADERSHIP_REVIEW_NEEDED",
    "PROJECT_READY_FOR_REVIEW", "PROJECT_COMPLETED", "PROJECT_QA_NAMED", "TASK_QA_ASSIGNED", "TASK_QA_REVIEW_NEEDED", "TASK_QA_APPROVED",
    "TASK_REVIEW_REJECTED", "TASK_REVIEW_APPROVED", "COMMENT_ADDED", "QUESTION_ASKED", "BLOCKER_RAISED", "BLOCKER_ESCALATED", "BLOCKER_REPLIED", "BLOCKER_RESOLVED",
    "PROJECT_MEMBER_ADDED", "PROJECT_CREATED", "PROJECT_DEADLINE_TOMORROW", "PROJECT_DEADLINE_TODAY", "PROJECT_DEADLINE_3H", "PROJECT_OVERDUE",
}  # fmt: skip


def attach_logo(msg: EmailMessage) -> None:
    """Attach the SeaWind logo inline as cid:seawind_logo so mail clients display it without broken image links."""
    html_part = msg.get_body("html")
    if html_part is None:
        return
    try:
        content = html_part.get_content()
    except Exception:
        content = ""
    if "cid:seawind_logo" not in content:
        return

    static_logo = Path(__file__).resolve().parents[2] / "static" / "seawind-logo.png"
    if not static_logo.exists():
        static_logo = Path(__file__).resolve().parents[4] / "frontend" / "public" / "seawind-logo.png"
    if static_logo.exists():
        try:
            data = static_logo.read_bytes()
            html_part.add_related(data, "image", "png", cid="<seawind_logo>", filename="seawind-logo.png")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not attach seawind-logo.png to email: %s", exc)


def _goes_now(db: Session, row: EmailLog) -> bool:
    if row.urgent:
        return True
    if row.notification_id is None:
        return False
    return db.scalar(select(Notification.event_type).where(Notification.id == row.notification_id)) in IMMEDIATE_EVENTS


def build_message(row: EmailLog) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = get_settings().email_from, row.to_email, row.subject
    sender = parseaddr(get_settings().email_from)[1]
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    msg["Auto-Submitted"] = "auto-generated"  # tells mail servers this is a system notice, not a person
    msg["X-Mailer"] = "SeaWind-TMS"
    if row.urgent:
        msg["Importance"] = "high"
    msg.set_content(row.body_text)
    msg.add_alternative(row.body_html, subtype="html")
    attach_logo(msg)
    return msg


def send_message(msg: EmailMessage) -> str:
    """Deliver one message with the configured backend. Returns the backend name. Raises on failure."""
    s = get_settings()
    if s.email_backend == "log":
        log.info("EMAIL (log backend) to=%s subject=%s\n%s", msg["To"], msg["Subject"], msg.get_body(("plain",)).get_content())
        return "log"
    if s.email_backend != "smtp" or not s.smtp_host:
        raise RuntimeError("Email is not configured: set TMS_EMAIL_BACKEND=smtp and TMS_SMTP_HOST")
    if s.smtp_security == "ssl":
        client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20)
    else:
        client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
    try:
        client.ehlo()
        if s.smtp_security == "starttls":
            client.starttls()
            client.ehlo()
        if s.smtp_user:
            client.login(s.smtp_user, s.smtp_password)
        client.send_message(msg)
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001
            pass
    return "smtp"


# ---------------------------------------------------------------- working-hours window


def _span(db: Session, d) -> tuple[time, time] | None:
    info = cal.day_info(db, d)
    return (info.windows[0][0], info.windows[-1][1]) if info.is_working and info.windows else None


def in_send_window(db: Session, now: datetime) -> bool:
    local = cal.utc_to_local(db, now)
    span = _span(db, local.date())
    return bool(span and span[0] <= local.time() <= span[1])


def next_window_start(db: Session, now: datetime) -> datetime:
    local = cal.utc_to_local(db, now)
    for i in range(0, 15):
        d = local.date() + timedelta(days=i)
        span = _span(db, d)
        if span and (i > 0 or local.time() < span[0]):
            return cal.local_to_utc(db, datetime.combine(d, span[0]))
    return now


# ---------------------------------------------------------------- dispatch


def _stale(db: Session, row: EmailLog) -> bool:
    """A reminder email waiting in the queue must not go out once its deadline moved or its task was finished."""
    if row.notification_id is None:
        return False
    n = db.get(Notification, row.notification_id)
    if n is None or n.event_type not in SCHEDULED:
        return False
    return not still_valid(db, n.event_type, db.get(Task, n.task_id) if n.task_id else None, version_of(n.dedupe_key))


def dispatch_emails(db: Session, now: datetime | None = None, limit: int = 50) -> dict:
    now = now or clock.utcnow()
    out = {"sent": 0, "retry": 0, "failed": 0, "deferred": 0, "skipped": 0}
    rows = db.scalars(select(EmailLog).where(EmailLog.status == "queued", EmailLog.next_attempt_at <= now).order_by(EmailLog.id).limit(limit).with_for_update()).all()
    window_open = in_send_window(db, now)
    for row in rows:
        if _stale(db, row):
            row.status, row.last_error = "skipped", "No longer relevant (deadline changed or task finished)"
            out["skipped"] += 1
            continue
        if real_mail_server() and is_reserved_recipient(row.to_email):  # never ask a real server to deliver to a fake address
            row.status, row.last_error = "skipped", "Reserved test address (example.com, .local, .test ...): not sent through a real mail server"
            out["skipped"] += 1
            continue
        if not window_open and not _goes_now(db, row):  # routine mail waits for working hours; the mail above does not
            row.next_attempt_at = next_window_start(db, now)
            out["deferred"] += 1
            continue
        try:
            row.backend = send_message(build_message(row))
            row.status, row.sent_at, row.last_error = "sent", now, None
            out["sent"] += 1
        except Exception as exc:  # noqa: BLE001
            row.attempts += 1
            row.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            if isinstance(exc, PERMANENT) or row.attempts >= MAX_ATTEMPTS:
                row.status = "failed"
                out["failed"] += 1
                record_failure(db, "email", row.last_error, {"email_log_id": row.id, "to": row.to_email})
            else:
                row.next_attempt_at = now + timedelta(seconds=BACKOFF_SECONDS[min(row.attempts - 1, len(BACKOFF_SECONDS) - 1)])
                out["retry"] += 1
        db.commit()  # settle this email now: a run killed half-way never re-sends the ones already done
    db.flush()
    return out
