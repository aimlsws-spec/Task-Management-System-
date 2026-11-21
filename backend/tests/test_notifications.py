"""Phase 6: the right people hear about the right things, exactly once, and failures never lose or duplicate anything."""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import ActivityLog
from app.modules.auth.models import User
from app.modules.notifications import service
from app.modules.notifications.models import EmailLog, Notification, NotificationRule, OutboxEvent

from .helpers import ABC, API, FINISH, SUPPORT, approve_through, at, do, make, ok


def relay(seeded):
    with seeded() as s:
        pushed = service.relay_outbox(s)
        s.commit()
    return pushed


def by_user(seeded, event_type):
    """{'abc': [Notification...]} for one event type."""
    with seeded() as s:
        rows = s.execute(select(User.email, Notification).join(Notification, Notification.user_id == User.id).where(Notification.event_type == event_type)).all()
    out: dict[str, list] = {}
    for email, n in rows:
        out.setdefault(email.split("@")[0], []).append(n)
    return out


def emails_to(seeded, event_type=None):
    with seeded() as s:
        q = select(User.email).join(EmailLog, EmailLog.to_user_id == User.id)
        if event_type:
            q = q.join(Notification, Notification.id == EmailLog.notification_id).where(Notification.event_type == event_type)
        return sorted(e.split("@")[0] for e in s.scalars(q))


# ---------------------------------------------------------------- who is told when a task is assigned


def test_owner_assigns_abc_tells_abc_manager_head_and_ceo_once_each(client, as_user, seeded):
    make(client, as_user, seeded, who="owner", assignee=ABC)
    relay(seeded)
    got = by_user(seeded, "TASK_CREATED")
    assert set(got) == {"abc", "devhead", "manager", "ceo"}  # the loop in the brief
    assert all(len(v) == 1 for v in got.values())  # never two notifications for one person
    assert {"DIRECT_MANAGER", "DEPARTMENT_HEAD"} <= set(got["devhead"][0].reasons)  # several reasons, ONE notification
    assert "ASSIGNEE" in got["abc"][0].reasons and "Develop AI Chatbot API" in got["abc"][0].title
    assert "owner" not in got and "hrhead" not in got and "support1" not in got  # not the actor, not unrelated people
    assert emails_to(seeded, "TASK_CREATED") == ["abc", "ceo", "devhead", "manager"]


def test_manager_assigning_does_not_involve_the_ceo_or_owner_by_default(client, as_user, seeded):
    make(client, as_user, seeded, who="manager", assignee=ABC)
    relay(seeded)
    assert set(by_user(seeded, "TASK_CREATED")) == {"abc", "devhead"}  # the Manager is the actor; CEO/Owner are configurable (off)


def test_a_department_without_a_head_reports_to_the_manager(client, as_user, seeded):
    make(client, as_user, seeded, who="owner", assignee=SUPPORT)
    relay(seeded)
    assert set(by_user(seeded, "TASK_CREATED")) == {"support1", "manager", "ceo"}  # no Support Head exists


def test_the_ceo_rule_for_manager_assignments_is_configurable(client, as_user, seeded):
    with seeded() as s:
        rule = s.scalar(select(NotificationRule).where(NotificationRule.event_type == "TASK_CREATED", NotificationRule.selector == "ROLE:ceo", NotificationRule.enabled.is_(False)))
        rid = rule.id
    r = client.patch(f"{API}/admin/notification-rules/{rid}", headers=as_user("admin"), json={"enabled": True})
    assert r.status_code == 200 and r.json()["enabled"] is True
    make(client, as_user, seeded, who="manager", assignee=ABC)
    relay(seeded)
    assert set(by_user(seeded, "TASK_CREATED")) == {"abc", "devhead", "ceo"}  # no code change: just a rule


def test_owner_and_ceo_cannot_edit_the_rules(client, as_user, seeded):
    for who in ("owner", "ceo", "manager"):
        assert client.get(f"{API}/admin/notification-rules", headers=as_user(who)).status_code == 403
    assert len(client.get(f"{API}/admin/notification-rules", headers=as_user("admin")).json()) > 50


def test_relaying_twice_never_duplicates(client, as_user, seeded):
    make(client, as_user, seeded)
    relay(seeded)
    first = by_user(seeded, "TASK_CREATED")
    relay(seeded)
    relay(seeded)
    again = by_user(seeded, "TASK_CREATED")
    assert {k: len(v) for k, v in first.items()} == {k: len(v) for k, v in again.items()}
    with seeded() as s:
        assert s.scalar(select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "pending")) == 0
        assert s.scalar(select(func.count(EmailLog.id))) == 4


def test_nothing_is_announced_for_an_action_that_failed(client, as_user, seeded):
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "acknowledge")
    assert do(client, as_user, "abc", t["id"], "acknowledge").status_code == 409  # refused: no state change
    with seeded() as s:
        assert s.scalar(select(func.count(OutboxEvent.id)).where(OutboxEvent.event_type == "TASK_ACKNOWLEDGED")) == 1  # transactional outbox


# ---------------------------------------------------------------- the other events in the brief's table


def test_acknowledge_start_and_complete_reach_the_right_people(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "acknowledge")
    ok(client, as_user, "abc", t["id"], "start")
    at(60)
    ok(client, as_user, "abc", t["id"], "pause")
    ok(client, as_user, "abc", t["id"], "start")  # a second start is NOT announced again
    at(120)
    ok(client, as_user, "abc", t["id"], "complete", FINISH)
    approve_through(client, as_user, t["id"])  # ADR 008: head, then CEO/Owner review it
    relay(seeded)
    assert set(by_user(seeded, "TASK_ACKNOWLEDGED")) == {"owner", "devhead"}  # who assigned it, and the line manager
    assert set(by_user(seeded, "TASK_STARTED")) == {"owner"} and len(by_user(seeded, "TASK_STARTED")["owner"]) == 1
    assert set(by_user(seeded, "TASK_HEAD_REVIEW_NEEDED")) == {"devhead"}  # the head is asked first
    assert {"abc", "devhead"} <= set(by_user(seeded, "TASK_REVIEW_APPROVED"))  # the employee hears the final result


def test_deadline_change_tells_everyone_above_and_the_assignee(client, as_user, seeded):
    t = make(client, as_user, seeded)
    body = {"due_date": str(date.today() + timedelta(days=9)), "reason": "Client asked for an extra integration"}
    assert client.post(f"{API}/tasks/{t['id']}/deadline", headers=as_user("manager"), json=body).status_code == 200
    relay(seeded)
    got = by_user(seeded, "TASK_DEADLINE_CHANGED")
    assert set(got) == {"abc", "devhead", "ceo", "owner"}  # the Manager made the change, so not them
    assert "Client asked for an extra integration" in got["abc"][0].body and got["abc"][0].urgent is True


def test_cancel_revert_and_priority_notify_the_assignee(client, as_user, seeded):
    at(0)
    a, b = make(client, as_user, seeded, title="Task one"), make(client, as_user, seeded, title="Task two")
    ok(client, as_user, "owner", a["id"], "cancel", {"reason": "No longer needed by the client"})
    ok(client, as_user, "manager", b["id"], "priority", {"priority": "critical", "reason": "Escalated"})
    ok(client, as_user, "abc", b["id"], "start")
    at(60)
    ok(client, as_user, "abc", b["id"], "complete", FINISH)
    ok(client, as_user, "devhead", b["id"], "revert", {"reason_code": "qa_defect", "reason": "Login fails on Safari", "found_by": "QA"})
    relay(seeded)
    assert "abc" in by_user(seeded, "TASK_CANCELLED") and by_user(seeded, "TASK_CANCELLED")["abc"][0].urgent
    assert "abc" in by_user(seeded, "TASK_PRIORITY_CHANGED")
    rev = by_user(seeded, "TASK_REVERTED")
    assert "abc" in rev and "Login fails on Safari" in rev["abc"][0].body and "owner" in rev  # the assigner is told too


def test_delay_explanation_reaches_management_and_confirms_to_the_employee(client, as_user, seeded):
    from .test_delays import explain, overdue_task

    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    relay(seeded)
    got = by_user(seeded, "DELAY_EXPLANATION_SUBMITTED")
    assert {"devhead", "manager", "abc"} <= set(got)  # head + Manager, and a confirmation to the employee
    assert not {"ceo", "owner"} & set(got)  # leadership is NOT told until the line approves the reason
    assert emails_to(seeded, "DELAY_EXPLANATION_SUBMITTED") == ["devhead", "manager"]
    from .test_delays import detail, review

    rid = detail(client, as_user, t["id"])["delay"]["items"][0]["id"]
    assert review(client, as_user, rid, "accepted", who="devhead").status_code == 200
    relay(seeded)
    released = by_user(seeded, "DELAY_RELEASED")
    assert {"ceo", "owner"} <= set(released)  # now the CEO and the Owner hear about it


# ---------------------------------------------------------------- reading, muting, and the unread count


def test_my_notifications_api(client, as_user, seeded):
    make(client, as_user, seeded)
    make(client, as_user, seeded, title="Second task")
    relay(seeded)
    h = as_user("abc")
    assert client.get(f"{API}/notifications/unread-count", headers=h).json() == {"unread": 2}
    page = client.get(f"{API}/notifications", headers=h).json()
    assert page["total"] == 2 and page["unread"] == 2 and page["items"][0]["title"].startswith("New task: Second task")
    nid = page["items"][0]["id"]
    assert client.put(f"{API}/notifications/{nid}/read", headers=h).json()["is_read"] is True
    assert client.get(f"{API}/notifications/unread-count", headers=h).json() == {"unread": 1}
    assert client.get(f"{API}/notifications", params={"unread": True}, headers=h).json()["total"] == 1
    assert client.post(f"{API}/notifications/read-all", headers=h).json() == {"marked": 1}
    assert client.get(f"{API}/notifications/unread-count", headers=h).json() == {"unread": 0}


def test_nobody_can_touch_someone_elses_notification(client, as_user, seeded):
    make(client, as_user, seeded)
    relay(seeded)
    nid = client.get(f"{API}/notifications", headers=as_user("abc")).json()["items"][0]["id"]
    assert client.put(f"{API}/notifications/{nid}/read", headers=as_user("devhead")).status_code == 404
    assert client.get(f"{API}/notifications", headers=as_user("hrhead")).json()["total"] == 0
    assert client.get(f"{API}/notifications").status_code == 401


def test_people_can_mute_optional_notices_but_never_mandatory_ones(client, as_user, seeded):
    prefs = {p["event_type"]: p for p in client.get(f"{API}/me/notification-preferences", headers=as_user("devhead")).json()}
    assert prefs["TASK_CREATED"]["in_app"] and prefs["TASK_CREATED"]["email"] and prefs["TASK_CREATED"]["locked"] is False
    assert prefs["TASK_REMINDER_24H"]["locked"] is True  # every reason to be told is mandatory
    for who in ("devhead", "abc"):  # devhead mutes the email; abc tries to mute everything
        for ch in ("email", "in_app"):
            r = client.put(f"{API}/me/notification-preferences", headers=as_user(who), json={"event_type": "TASK_CREATED", "channel": ch, "enabled": False})
            assert r.status_code == 200
    make(client, as_user, seeded)
    relay(seeded)
    got = by_user(seeded, "TASK_CREATED")
    assert "abc" in got  # the assignee's notice is mandatory: muting does nothing
    assert "devhead" not in got  # their only reasons were optional and both channels are muted
    assert "abc" in emails_to(seeded, "TASK_CREATED") and "devhead" not in emails_to(seeded, "TASK_CREATED")


def test_muting_one_channel_keeps_the_other(client, as_user, seeded):
    client.put(f"{API}/me/notification-preferences", headers=as_user("manager"), json={"event_type": "TASK_CREATED", "channel": "email", "enabled": False})
    make(client, as_user, seeded)
    relay(seeded)
    assert "manager" in by_user(seeded, "TASK_CREATED") and "manager" not in emails_to(seeded, "TASK_CREATED")


def test_deactivated_people_are_never_notified(client, as_user, seeded):
    with seeded() as s:
        u = s.scalar(select(User).where(User.email == "ceo@demo.example.com"))
        u.is_active = False
        s.commit()
    make(client, as_user, seeded)
    relay(seeded)
    assert "ceo" not in by_user(seeded, "TASK_CREATED")


def test_audit_trail_is_unchanged_by_notifications(client, as_user, seeded):
    t = make(client, as_user, seeded)
    with seeded() as s:
        assert s.scalar(select(func.count(ActivityLog.id)).where(ActivityLog.task_id == t["id"])) == 1


_ = pytest
