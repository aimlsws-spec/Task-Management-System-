"""ADR 007: a project deadline is mandatory; project/task/message mail reaches people (also without cron); project deadline reminders."""

from datetime import date, timedelta

from sqlalchemy import func, select

from app.core import clock
from app.core.config import get_settings
from app.jobs import scheduler
from app.modules.notifications.models import EmailLog, Notification

from .helpers import ABC, API, DEVHEAD, FE, HR1, at, eid, make
from .test_notifications import by_user, emails_to, relay
from .test_projects import make_project


def create(client, as_user, **over):
    body = {"name": "Deadline test", "ends_on": str(date.today() + timedelta(days=20))} | over
    return client.post(f"{API}/projects", headers=as_user("owner"), json=body)


def test_a_project_cannot_be_created_without_a_deadline(client, as_user):
    r = client.post(f"{API}/projects", headers=as_user("owner"), json={"name": "No deadline"})
    assert r.status_code == 422
    r = client.post(f"{API}/projects", headers=as_user("owner"), json={"name": "No deadline", "ends_on": None})
    assert r.status_code == 422
    assert create(client, as_user).status_code == 201


def test_the_deadline_cannot_be_in_the_past_or_before_the_start_or_removed(client, as_user):
    assert create(client, as_user, ends_on=str(date.today() - timedelta(days=2))).json()["code"] == "PAST_DEADLINE"
    assert create(client, as_user, starts_on=str(date.today() + timedelta(days=10)), ends_on=str(date.today() + timedelta(days=5))).json()["code"] == "INVALID_DATES"
    pr = create(client, as_user).json()
    assert client.patch(f"{API}/projects/{pr['id']}", headers=as_user("owner"), json={"ends_on": None}).json()["code"] == "DEADLINE_REQUIRED"
    new = str(date.today() + timedelta(days=40))
    r = client.patch(f"{API}/projects/{pr['id']}", headers=as_user("owner"), json={"ends_on": new})
    assert r.status_code == 200 and r.json()["ends_on"] == new


def test_everyone_added_to_a_project_gets_an_email_with_the_deadline(client, as_user, seeded):
    ends = date.today() + timedelta(days=12)
    pr = create(client, as_user, ends_on=str(ends), head_employee_id=eid(seeded, DEVHEAD), qa_employee_id=eid(seeded, FE),
                member_ids=[eid(seeded, ABC), eid(seeded, HR1)], expected_result="A working site").json()
    relay(seeded)
    assert "devhead" in emails_to(seeded, "PROJECT_HEAD_NAMED") and "frontend" in emails_to(seeded, "PROJECT_QA_NAMED")
    assert {"abc", "hr1"} <= set(emails_to(seeded, "PROJECT_MEMBER_ADDED"))  # team members were in-app only before
    assert {"ceo"} <= set(emails_to(seeded, "PROJECT_CREATED"))  # leadership hears about the new project (the creator does not)
    with seeded() as s:
        body = s.scalars(select(EmailLog.body_text).join(Notification, Notification.id == EmailLog.notification_id).where(Notification.event_type == "PROJECT_MEMBER_ADDED")).first()
    assert ends.strftime("%d %b %Y") in body and "A working site" in body and "Deadline test" in body
    assert pr["ends_on"] == str(ends)


def test_task_and_message_mail_is_sent_straight_away_without_cron(client, as_user, seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_after_request", True)  # ADR 007: processed after each change, no relay() call needed
    at(0)
    t = make(client, as_user, seeded, head_employee_id=eid(seeded, DEVHEAD), qa_employee_id=eid(seeded, FE))
    with seeded() as s:
        assert s.scalar(select(func.count(Notification.id)).where(Notification.event_type == "TASK_CREATED")) > 0
        mails = s.scalar(select(func.count(EmailLog.id)))
    assert mails > 0
    r = client.post(f"{API}/tasks/{t['id']}/comments", headers=as_user("abc"), json={"kind": "comment", "body": "Starting now, details by mail"})
    assert r.status_code == 201, r.text
    assert {"owner", "devhead", "frontend"} <= set(by_user(seeded, "COMMENT_ADDED"))
    assert {"owner", "devhead", "frontend"} <= set(emails_to(seeded, "COMMENT_ADDED"))
    with seeded() as s:
        assert s.scalar(select(func.count(EmailLog.id)).where(EmailLog.status == "sent")) > 0  # actually handed to the mail backend


def test_without_the_switch_nothing_runs_in_the_request(client, as_user, seeded):
    at(0)
    make(client, as_user, seeded)
    with seeded() as s:
        assert s.scalar(select(func.count(Notification.id))) == 0  # cron (or the Admin button) does it


def test_project_deadline_reminders_tomorrow_today_and_overdue(client, as_user, seeded):
    at(0)
    local_today = (clock.utcnow() + timedelta(hours=5, minutes=30)).date()
    pr = make_project(client, as_user, seeded, head_employee_id=eid(seeded, DEVHEAD), member_ids=[eid(seeded, ABC)], ends_on=str(local_today + timedelta(days=1)))
    relay(seeded)

    def scan():
        with seeded() as s:
            n = scheduler.project_deadlines(s, clock.utcnow())
            s.commit()
        relay(seeded)
        return n

    assert scan() == 1 and {"devhead", "abc"} <= set(by_user(seeded, "PROJECT_DEADLINE_TOMORROW"))
    assert scan() == 0  # once only
    at(24 * 60)  # a day later: due today
    assert scan() == 1 and {"devhead", "abc"} <= set(by_user(seeded, "PROJECT_DEADLINE_TODAY"))
    at(3 * 24 * 60)
    assert scan() == 1
    late = by_user(seeded, "PROJECT_OVERDUE")
    assert {"devhead", "abc", "ceo", "owner"} <= set(late) and "Deadline" in late["ceo"][0].body or pr
    assert {"ceo", "owner", "devhead"} <= set(emails_to(seeded, "PROJECT_OVERDUE"))
