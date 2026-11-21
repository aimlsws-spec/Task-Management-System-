"""Phase 6: email delivery (real SMTP against a local server), retries, working hours, the scheduler and live push."""

import smtplib
import socket
from datetime import date, datetime, time, timedelta

import pytest
from aiosmtpd.controller import Controller
from sqlalchemy import select, text

from app.core import clock
from app.core.config import get_settings
from app.jobs import scheduler
from app.modules.audit.models import SystemSetting
from app.modules.notifications import mailer, reminders
from app.modules.notifications.models import EmailLog, JobFailure
from app.modules.timetracking.guard import run_guard

from .helpers import API, at, make, ok
from .test_notifications import by_user, emails_to, relay


def mk(client, as_user, seeded, **over):
    """A task whose deadline is well after the (frozen) moment each test runs at."""
    return make(client, as_user, seeded, **({"due_date": str(MON + timedelta(days=5))} | over))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Inbox:
    def __init__(self):
        self.messages: list = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802 - aiosmtpd's hook name
        self.messages.append(envelope)
        return "250 OK"


@pytest.fixture()
def smtp_server(monkeypatch):
    inbox = Inbox()
    port = free_port()
    ctl = Controller(inbox, hostname="127.0.0.1", port=port)
    ctl.start()
    s = get_settings()
    for k, v in {"email_backend": "smtp", "smtp_host": "127.0.0.1", "smtp_port": port, "smtp_security": "none", "smtp_user": ""}.items():
        monkeypatch.setattr(s, k, v)
    yield inbox
    ctl.stop()


def dispatch(seeded, now=None):
    with seeded() as s:
        out = mailer.dispatch_emails(s, now or clock.utcnow())
        s.commit()
    return out


def rows(seeded):
    with seeded() as s:
        return s.scalars(select(EmailLog).order_by(EmailLog.id)).all()


def _next_monday() -> date:
    d = date.today() + timedelta(days=3)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


MON = _next_monday()
MON_11AM = datetime.combine(MON, time(5, 30))  # a future Monday, 11:00 IST: inside working hours
SUN_11AM = datetime.combine(MON - timedelta(days=1), time(5, 30))  # the Sunday before it: a day off
MON_OPENS = datetime.combine(MON, time(4, 0))  # Monday 09:30 IST


# ---------------------------------------------------------------- the email itself


def test_emails_really_go_out_over_smtp(client, as_user, seeded, smtp_server):
    clock.freeze(MON_11AM)  # emails are created, and judged, at a working-hours moment
    mk(client, as_user, seeded, title="Build the report")
    relay(seeded)
    out = dispatch(seeded, MON_11AM)
    assert out["sent"] == 4 and out["failed"] == 0
    assert sorted(m.rcpt_tos[0].split("@")[0] for m in smtp_server.messages) == ["abc", "ceo", "devhead", "manager"]
    msg = next(m for m in smtp_server.messages if m.rcpt_tos[0].startswith("abc")).content.decode()
    assert "Subject: [SeaWind] New task: Build the report" in msg and "text/html" in msg and "Open the task" in msg
    assert all(r.status == "sent" and r.backend == "smtp" and r.sent_at for r in rows(seeded))


def test_email_html_escapes_user_text(client, as_user, seeded, smtp_server):
    clock.freeze(MON_11AM)  # emails are created, and judged, at a working-hours moment
    mk(client, as_user, seeded, title="<script>alert(1)</script>")
    relay(seeded)
    dispatch(seeded, MON_11AM)
    import email
    from email import policy

    raw = next(m for m in smtp_server.messages if m.rcpt_tos[0].startswith("abc")).content
    msg = email.message_from_bytes(raw, policy=policy.default)
    html = msg.get_body(("html",)).get_content()
    assert "<script>" not in html and "&lt;script&gt;" in html  # nobody can inject markup into the HTML email
    assert "<script>alert(1)</script>" in msg.get_body(("plain",)).get_content()  # plain text is shown as typed, never rendered


def test_log_backend_is_the_safe_default(client, as_user, seeded):
    clock.freeze(MON_11AM)  # emails are created, and judged, at a working-hours moment
    mk(client, as_user, seeded)
    relay(seeded)
    assert dispatch(seeded, MON_11AM)["sent"] == 4
    assert {r.backend for r in rows(seeded)} == {"log"}


# ---------------------------------------------------------------- failures: retry with backoff, then give up visibly


def test_unreachable_mail_server_retries_with_backoff_then_fails_visibly(client, as_user, seeded, monkeypatch):
    clock.freeze(MON_11AM)
    s = get_settings()
    for k, v in {"email_backend": "smtp", "smtp_host": "127.0.0.1", "smtp_port": free_port(), "smtp_security": "none"}.items():
        monkeypatch.setattr(s, k, v)  # nothing is listening there
    mk(client, as_user, seeded)
    relay(seeded)
    now, waits = MON_11AM, []
    for attempt in range(1, 6):
        out = dispatch(seeded, now)
        row = rows(seeded)[0]
        assert row.attempts == attempt and row.last_error
        if attempt < 5:
            assert row.status == "queued" and out["retry"] == 4
            waits.append(int((row.next_attempt_at - now).total_seconds()))
            now = row.next_attempt_at
    assert waits == [60, 300, 1800, 7200]  # 1 min, 5 min, 30 min, 2 h
    assert all(r.status == "failed" for r in rows(seeded))  # the 5th failure is final
    with seeded() as s2:
        failures = s2.scalars(select(JobFailure).where(JobFailure.job == "email")).all()
        assert len(failures) == 4 and "Connection" in failures[0].error or "refused" in failures[0].error.lower()


def test_failed_email_never_blocks_the_in_app_notification_and_can_be_retried(client, as_user, seeded, monkeypatch):
    clock.freeze(MON_11AM)  # emails are created, and judged, at a working-hours moment
    s = get_settings()
    monkeypatch.setattr(s, "email_backend", "smtp")
    monkeypatch.setattr(s, "smtp_host", "")  # misconfigured
    mk(client, as_user, seeded)
    relay(seeded)
    dispatch(seeded, MON_11AM)
    assert len(by_user(seeded, "TASK_CREATED")) == 4  # everyone still has their in-app notification
    assert "not configured" in rows(seeded)[0].last_error
    first = rows(seeded)[0]
    r = client.post(f"{API}/admin/email-logs/{first.id}/retry", headers=as_user("admin"))
    assert r.status_code == 200 and r.json()["status"] == "queued"
    assert client.post(f"{API}/admin/email-logs/{first.id}/retry", headers=as_user("owner")).status_code == 403


def test_a_refused_recipient_fails_immediately_without_retrying(client, as_user, seeded, monkeypatch):
    clock.freeze(MON_11AM)  # emails are created, and judged, at a working-hours moment
    def refuse(msg):
        raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no such user")})

    monkeypatch.setattr(mailer, "send_message", refuse)
    mk(client, as_user, seeded)
    relay(seeded)
    out = dispatch(seeded, MON_11AM)
    assert out["failed"] == 4 and out["retry"] == 0 and all(r.attempts == 1 and r.status == "failed" for r in rows(seeded))


# ---------------------------------------------------------------- working hours


def test_task_emails_are_sent_at_once_even_outside_working_hours(client, as_user, seeded):
    """Assigned / reminder / overdue / explanation emails never wait for Monday (the product owner's decision)."""
    clock.freeze(SUN_11AM)
    mk(client, as_user, seeded)
    relay(seeded)
    assert dispatch(seeded, SUN_11AM) == {"sent": 4, "retry": 0, "failed": 0, "deferred": 0, "skipped": 0}


def test_urgent_email_ignores_the_working_hours_window(client, as_user, seeded):
    with seeded() as s:
        for urgent in (True, False):
            s.add(EmailLog(to_email="abc@demo.example.com", subject=f"urgent={urgent}", body_text="x", body_html="<p>x</p>", urgent=urgent,
                           next_attempt_at=SUN_11AM - timedelta(hours=1)))  # fmt: skip
        s.commit()
    out = dispatch(seeded, SUN_11AM)  # a Sunday: the window is closed
    assert out["sent"] == 1 and out["deferred"] == 1
    by_subject = {r.subject: r.status for r in rows(seeded)}
    assert by_subject == {"urgent=True": "sent", "urgent=False": "queued"}  # an overdue notice cannot wait for Monday


def test_the_send_window_matches_the_work_calendar(db):
    assert mailer.in_send_window(db, MON_11AM) and not mailer.in_send_window(db, SUN_11AM)
    assert not mailer.in_send_window(db, datetime(2026, 11, 16, 13, 30))  # 19:00 IST: after hours
    assert not mailer.in_send_window(db, datetime(2026, 11, 14, 5, 30))  # the 2nd Saturday is a day off
    assert mailer.next_window_start(db, datetime(2026, 11, 14, 5, 30)) == datetime(2026, 11, 16, 4, 0)  # skips Sat and Sun


# ---------------------------------------------------------------- forgotten timers become notifications


def test_checkins_and_auto_stop_notify_the_employee_once(client, as_user, seeded):
    at(0)
    t = mk(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    from .helpers import BASE

    with seeded() as s:
        run_guard(s, BASE + timedelta(hours=4, minutes=5))
        s.commit()
        run_guard(s, BASE + timedelta(hours=4, minutes=6))  # again: still one
        s.commit()
        run_guard(s, BASE + timedelta(hours=8, minutes=5))  # the 8 h prompt
        s.commit()
        clock.freeze(BASE + timedelta(hours=11))
        run_guard(s, BASE + timedelta(hours=11))
        s.commit()
    relay(seeded)
    checkins = by_user(seeded, "TIMER_CHECKIN")["abc"]
    assert len(checkins) == 2 and "Still working on" in checkins[0].title  # after 4 h and after 8 h, one each
    assert len(by_user(seeded, "TIMER_AUTO_CLOSED")["abc"]) == 1 and "abc" in emails_to(seeded, "TIMER_AUTO_CLOSED")


def test_unconfirmed_auto_stopped_time_alerts_the_manager_after_three_days_once(client, as_user, seeded):
    from .helpers import BASE

    at(0)
    t = mk(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    client.get(f"{API}/time/active", headers=as_user("abc"))  # contact at start: nothing closed yet
    at(12 * 60)
    client.get(f"{API}/time/active", headers=as_user("abc"))  # closes the forgotten timer
    with seeded() as s:
        assert scheduler._alert_unconfirmed(s, BASE + timedelta(days=2)) == 0  # not yet three days
        s.commit()
        assert scheduler._alert_unconfirmed(s, BASE + timedelta(days=4)) == 1
        s.commit()
        assert scheduler._alert_unconfirmed(s, BASE + timedelta(days=5)) == 0  # never repeated
        s.commit()
    relay(seeded)
    assert "devhead" in by_user(seeded, "TIME_UNCONFIRMED_3D")


# ---------------------------------------------------------------- the scheduler


def test_one_tick_runs_everything_and_records_status(client, as_user, seeded):
    clock.freeze(MON_11AM)  # emails are created, and judged, at a working-hours moment
    mk(client, as_user, seeded)
    with seeded() as s:
        out = scheduler.tick(s, scan=False)
        assert out["notified"] == 4 and out["emails"]["sent"] == 4
        assert s.get(SystemSetting, "scheduler_status").value["last_tick_at"]


def test_a_failing_step_is_recorded_and_does_not_stop_the_others(client, as_user, seeded, monkeypatch):
    clock.freeze(MON_11AM)
    def boom(db, now):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(reminders, "scan", boom)
    mk(client, as_user, seeded)
    with seeded() as s:
        out = scheduler.tick(s)
        assert out["notified"] == 4  # notifications still went out
        failure = s.scalar(select(JobFailure).where(JobFailure.job == "reminder_scan"))
        assert failure and "scanner exploded" in failure.error
    failures = client.get(f"{API}/admin/jobs/failures", headers=as_user("admin")).json()
    assert failures[0]["job"] == "reminder_scan"


def test_only_one_scheduler_can_run_at_a_time(seeded):
    with seeded() as a, seeded() as b:
        name = scheduler.lock_name(a)
        assert name.startswith("tms_scheduler:") and name == scheduler.lock_name(b)  # the name carries the database
        assert a.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": name}).scalar() == 1
        assert b.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": name}).scalar() == 0  # the second one stays idle
        a.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": name})


def test_schedulers_for_different_databases_do_not_block_each_other(seeded):
    with seeded() as a, seeded() as b:
        mine = scheduler.lock_name(a)
        other = mine.replace(mine.split(":")[1], "some_other_db")  # e.g. the dev database on the same MySQL server
        assert a.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": mine}).scalar() == 1
        assert b.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": other}).scalar() == 1  # independent
        a.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": mine})
        b.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": other})


def test_admin_job_controls(client, as_user, seeded):
    clock.freeze(MON_11AM)  # emails are created, and judged, at a working-hours moment
    mk(client, as_user, seeded)
    status = client.get(f"{API}/admin/jobs/status", headers=as_user("admin")).json()
    assert status["pending_events"] >= 1 and status["email_backend"] == "log"
    assert client.get(f"{API}/admin/jobs/status", headers=as_user("owner")).status_code == 403
    assert client.post(f"{API}/admin/jobs/run-now", headers=as_user("manager")).status_code == 403
    r = client.post(f"{API}/admin/jobs/run-now", headers=as_user("admin"))
    assert r.status_code == 200 and r.json()["notified"] == 4
    assert client.get(f"{API}/admin/jobs/status", headers=as_user("admin")).json()["pending_events"] == 0
    logs = client.get(f"{API}/admin/email-logs", params={"status": "sent"}, headers=as_user("admin")).json()
    assert logs["total"] == 4 and logs["items"][0]["backend"] == "log"


# ---------------------------------------------------------------- never ask a real mail server to deliver to a fake address


def test_reserved_test_addresses_are_never_sent_through_a_real_mail_server(client, as_user, seeded, monkeypatch):
    s = get_settings()
    for k, v in {"email_backend": "smtp", "smtp_host": "mail.some-real-provider.org"}.items():
        monkeypatch.setattr(s, k, v)  # a real (non-loopback) server
    sent: list[str] = []
    monkeypatch.setattr(mailer, "send_message", lambda msg: sent.append(msg["To"]) or "smtp")
    with seeded() as db:
        for addr in ("abc@demo.example.com", "x@staging.local", "y@thing.test", "real.person@company.org"):
            db.add(EmailLog(to_email=addr, subject=addr, body_text="x", body_html="<p>x</p>", urgent=True, next_attempt_at=MON_11AM - timedelta(hours=1)))
        db.commit()
    out = dispatch(seeded, MON_11AM)
    assert sent == ["real.person@company.org"]  # only the genuine address went out
    assert out["sent"] == 1 and out["skipped"] == 3
    skipped = [r for r in rows(seeded) if r.status == "skipped"]
    assert len(skipped) == 3 and all("Reserved test address" in r.last_error for r in skipped)


def test_reserved_address_check():
    for bad in ("a@example.com", "a@demo.example.com", "a@example.org", "a@corp.local", "a@x.test", "a@y.invalid"):
        assert mailer.is_reserved_recipient(bad), bad
    for good in ("a@viralkar.in", "a@gmail.com", "a@notexample.com", "a@company.co.in"):
        assert not mailer.is_reserved_recipient(good), good
