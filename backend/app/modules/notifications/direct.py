"""Emails sent straight to a person because of an account change (invitation, added by the Admin, new role, department head,
welcome). They are queued like every other email (retries, log, Admin page) and are never held for working hours.
No password is ever put in an email."""

import logging
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.modules.notifications import mailer, templates
from app.modules.notifications.models import EmailLog

log = logging.getLogger("tms.notifications.direct")


def _queue(db: Session, to_email: str, to_user_id: int | None, subject: str, body: str, path: str, cta: str) -> None:
    base = get_settings().app_base_url.rstrip("/")
    title = subject.removeprefix("[SeaWind] ")
    text, html = templates.email_bodies(title, body, base + path, False, cta)
    row = EmailLog(to_user_id=to_user_id, to_email=to_email, subject=subject[:255], body_text=text, body_html=html, urgent=True,
                    next_attempt_at=clock.utcnow())
    db.add(row)
    db.flush()
    if mailer.real_mail_server() and not mailer.is_reserved_recipient(to_email):
        try:
            row.backend = mailer.send_message(mailer.build_message(row))
            row.status = "sent"
            row.sent_at = clock.utcnow()
            row.last_error = None
        except Exception as exc:
            log.warning("Immediate direct email delivery to %s failed: %s", to_email, exc)
            row.last_error = f"{type(exc).__name__}: {exc}"[:1000]


def invitation(db: Session, role_name: str, email: str, has_account: bool, user_id: int | None) -> None:
    if has_account:
        _queue(db, email, user_id, f"[SeaWind] You are now {role_name} in SeaWind Task Management",
               f"The administrator made you {role_name}. Sign in again to use your new access.", "/login", "Sign in")
    else:
        _queue(db, email, user_id, f"[SeaWind] You are invited to SeaWind Task Management as {role_name}",
               f"The administrator invited you to join as {role_name}. Create your account with this email address ({email}) "
               "and your role is set up automatically.", "/signup", "Create your account")


def added_by_admin(db: Session, email: str, user_id: int, full_name: str, role_names: list[str], dept_name: str) -> None:
    roles = ", ".join(role_names) or "Employee"
    _queue(db, email, user_id, f"[SeaWind] Your SeaWind Task Management account is ready ({roles})",
           f"Hello {full_name}, the administrator created your account as {roles} in {dept_name}. Sign in with this email address ({email}) "
           "and the temporary password the administrator gave you. You will be asked to choose your own password.", "/login", "Sign in")


def role_changed(db: Session, email: str, user_id: int, role_names: list[str]) -> None:
    roles = ", ".join(role_names) or "Employee"
    _queue(db, email, user_id, f"[SeaWind] Your role is now {roles}",
           f"The administrator changed your role to {roles}. Sign in again to use your new access.", "/login", "Sign in")


def head_named(db: Session, email: str, user_id: int, dept_name: str) -> None:
    _queue(db, email, user_id, f"[SeaWind] You are now the head of {dept_name}",
           f"The administrator made you the head of {dept_name}. Your team will report to you and you will be told about their tasks. "
           "Sign in again to use your new access.", "/login", "Sign in")


def welcome(db: Session, email: str, user_id: int, full_name: str, role_name: str, needs_onboarding: bool = True) -> None:
    if needs_onboarding:
        body = f"Hello {full_name}, your account is created ({role_name}). Sign in to finish setting up: choose your department and designation."
    else:
        body = f"Hello {full_name}, your account is created as {role_name}. Sign in to access your dashboard."
    _queue(db, email, user_id, "[SeaWind] Welcome to SeaWind Task Management", body, "/login", "Sign in")
