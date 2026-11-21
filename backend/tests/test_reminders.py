"""Phase 6: deadline reminders and escalations fire exactly once, at the right moment, to the right people,
and an old schedule can never speak after a deadline changed or the task was finished."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core import clock
from app.modules.notifications import service
from app.modules.notifications.models import EmailLog, Notification, OutboxEvent, ReminderLog, ReminderRule
from app.modules.notifications.reminders import scan
from app.modules.tasks.delays import escalation_times

from .helpers import API, FINISH, at, make, ok
from .test_notifications import by_user, emails_to, relay


def due_of(t) -> datetime:
    return datetime.fromisoformat(t["due_at"].rstrip("Z"))


def scan_at(seeded, when: datetime) -> dict:
    clock.freeze(when)
    with seeded() as s:
        fired = scan(s, when)
        s.commit()
    return fired


def pending_events(seeded, event_type):
    with seeded() as s:
        return s.scalars(select(OutboxEvent).where(OutboxEvent.event_type == event_type)).all()


# ---------------------------------------------------------------- before the deadline


def test_reminders_fire_at_24h_and_2h_and_only_once(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    d = due_of(t)
    assert scan_at(seeded, d - timedelta(hours=25)) == {}  # too early
    assert scan_at(seeded, d - timedelta(hours=23, minutes=50)) == {"before_24h": 1}
    assert scan_at(seeded, d - timedelta(hours=23)) == {}  # running the scanner again changes nothing
    assert scan_at(seeded, d - timedelta(hours=3)) == {}
    assert scan_at(seeded, d - timedelta(hours=1, minutes=50)) == {"before_2h": 1}
    assert scan_at(seeded, d - timedelta(hours=1)) == {}
    relay(seeded)
    assert set(by_user(seeded, "TASK_REMINDER_24H")) == {"abc"} and len(by_user(seeded, "TASK_REMINDER_24H")["abc"]) == 1
    assert set(by_user(seeded, "TASK_REMINDER_2H")) == {"abc"} and by_user(seeded, "TASK_REMINDER_2H")["abc"][0].urgent
    assert "Due in 24 hours" in by_user(seeded, "TASK_REMINDER_24H")["abc"][0].title
    assert emails_to(seeded, "TASK_REMINDER_24H") == ["abc"]


def test_a_task_given_only_a_few_hours_gets_no_24h_reminder(client, as_user, seeded):
    at(0)  # 09:30 IST
    t = make(client, as_user, seeded, due_date=str(clock.utcnow().date()))  # due at 18:30, 9 hours away
    d = due_of(t)
    assert scan_at(seeded, BASE_PLUS(2)) == {}  # "24 h before" would be in the past: never sent
    assert scan_at(seeded, d - timedelta(hours=1, minutes=50)) == {"before_2h": 1}  # the 2 h one is still meaningful


def BASE_PLUS(minutes):
    from .helpers import BASE

    return BASE + timedelta(minutes=minutes)


def test_two_scanners_cannot_both_send_the_same_reminder(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    scan_at(seeded, due_of(t) - timedelta(hours=23))
    with seeded() as s:
        log = s.scalar(select(ReminderLog))
        s.add(ReminderLog(task_id=log.task_id, rule_id=log.rule_id, deadline_version=log.deadline_version, assignee_id=log.assignee_id))
        with pytest.raises(IntegrityError):
            s.flush()  # the unique key is what makes it exactly-once, even for parallel runs


# ---------------------------------------------------------------- at the deadline and after


def test_overdue_notice_goes_to_the_whole_chain(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    assert scan_at(seeded, due_of(t) + timedelta(minutes=1)) == {"at_due": 1}
    assert scan_at(seeded, due_of(t) + timedelta(minutes=30)) == {}
    relay(seeded)
    got = by_user(seeded, "TASK_OVERDUE")
    assert set(got) == {"abc", "devhead", "manager", "ceo", "owner"}  # employee, head, Manager, CEO and Owner
    assert all(len(v) == 1 and v[0].urgent for v in got.values())
    assert emails_to(seeded, "TASK_OVERDUE") == ["abc", "ceo", "devhead", "manager", "owner"]


def test_escalations_follow_working_days_and_tiers(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    d = due_of(t)
    with seeded() as s:
        tiers = {code: when for _lvl, code, when in escalation_times(s, d)}
    assert scan_at(seeded, d + timedelta(minutes=1)) == {"at_due": 1}
    assert scan_at(seeded, tiers["after_1d"] - timedelta(minutes=1)) == {}
    assert scan_at(seeded, tiers["after_1d"]) == {"after_1d": 1}
    assert scan_at(seeded, tiers["after_3d"]) == {"after_3d": 1}
    assert scan_at(seeded, tiers["after_7d"] - timedelta(minutes=1)) == {}
    assert scan_at(seeded, tiers["after_7d"]) == {"after_7d": 1}
    assert scan_at(seeded, tiers["after_7d"] + timedelta(days=30)) == {}  # nothing repeats
    relay(seeded)
    assert set(by_user(seeded, "TASK_ESCALATION_1")) == {"abc"}  # +1 working day: another reminder to the employee
    assert set(by_user(seeded, "TASK_ESCALATION_2")) == {"devhead", "manager", "ceo", "abc"}  # +3: Manager and CEO (abc in-app only)
    assert "owner" not in by_user(seeded, "TASK_ESCALATION_2")
    assert set(by_user(seeded, "TASK_ESCALATION_3")) == {"devhead", "manager", "ceo", "owner", "abc"}  # +7: the Owner as well
    assert "abc" not in emails_to(seeded, "TASK_ESCALATION_2")  # the employee only gets it in the app


def test_the_reminder_timing_is_editable_by_the_admin(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    rules = {r["code"]: r for r in client.get(f"{API}/admin/reminder-rules", headers=as_user("admin")).json()}
    assert client.patch(f"{API}/admin/reminder-rules/{rules['before_24h']['id']}", headers=as_user("manager"), json={"minutes": 720}).status_code == 403
    r = client.patch(f"{API}/admin/reminder-rules/{rules['before_24h']['id']}", headers=as_user("admin"), json={"minutes": 720})
    assert r.status_code == 200 and r.json()["minutes"] == 720
    assert scan_at(seeded, due_of(t) - timedelta(hours=20)) == {}  # no longer 24 h before...
    assert scan_at(seeded, due_of(t) - timedelta(hours=11)) == {"before_24h": 1}  # ...now 12 h before


# ---------------------------------------------------------------- when NOT to remind


@pytest.mark.parametrize("prepare", ["hold", "review", "cancel", "complete"])
def test_no_reminders_for_paused_waiting_cancelled_or_finished_tasks(client, as_user, seeded, prepare):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(60)
    if prepare == "hold":
        ok(client, as_user, "abc", t["id"], "hold", {"reason": "Waiting for the client"})
    elif prepare == "review":
        ok(client, as_user, "abc", t["id"], "submit-for-review", FINISH)
    elif prepare == "cancel":
        ok(client, as_user, "owner", t["id"], "cancel", {"reason": "No longer needed"})
    else:
        ok(client, as_user, "abc", t["id"], "complete", FINISH)
    d = due_of(t)
    for when in (d - timedelta(hours=23), d - timedelta(hours=1), d + timedelta(minutes=5), d + timedelta(days=10)):
        assert scan_at(seeded, when) == {}, prepare
    with seeded() as s:
        assert s.scalars(select(ReminderLog)).all() == []


# ---------------------------------------------------------------- an old schedule can never speak after a change


def test_a_new_deadline_starts_a_fresh_schedule(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, due_date=str(date.today() + timedelta(days=5)))
    old_due = due_of(t)
    assert scan_at(seeded, old_due - timedelta(hours=23)) == {"before_24h": 1}
    body = {"due_date": str(date.today() + timedelta(days=9)), "reason": "Client asked for an extra integration"}
    clock.freeze(old_due - timedelta(hours=20))
    assert client.post(f"{API}/tasks/{t['id']}/deadline", headers=as_user("manager"), json=body).status_code == 200
    assert scan_at(seeded, old_due + timedelta(minutes=5)) == {}  # the old deadline passes: nothing, the task is not late
    new_due = due_of(client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json() | {"due_at": client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["due_at"]})
    assert scan_at(seeded, new_due - timedelta(hours=23)) == {"before_24h": 1}  # a fresh 24 h reminder for the NEW deadline
    with seeded() as s:
        versions = sorted(r.deadline_version for r in s.scalars(select(ReminderLog)))
    assert versions == [1, 2]


def test_a_pending_overdue_notice_is_dropped_if_the_deadline_moved_before_it_was_delivered(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    d = due_of(t)
    assert scan_at(seeded, d + timedelta(minutes=2)) == {"at_due": 1}  # the event exists but nobody has been told yet
    body = {"due_date": str(date.today() + timedelta(days=9)), "reason": "Extended just in time"}
    assert client.post(f"{API}/tasks/{t['id']}/deadline", headers=as_user("manager"), json=body).status_code == 200
    relay(seeded)
    assert by_user(seeded, "TASK_OVERDUE") == {}  # stale: it described a deadline that no longer exists
    assert pending_events(seeded, "TASK_OVERDUE")[0].status == "skipped"


def test_a_pending_overdue_notice_is_dropped_if_the_task_was_completed_meanwhile(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    d = due_of(t)
    scan_at(seeded, d + timedelta(minutes=2))
    clock.freeze(d + timedelta(minutes=3))
    ok(client, as_user, "abc", t["id"], "complete", FINISH | {"late_reason": "Finished a few minutes late"})
    relay(seeded)
    assert by_user(seeded, "TASK_OVERDUE") == {}


def test_a_queued_reminder_email_is_not_sent_after_the_task_is_finished(client, as_user, seeded):
    from app.modules.notifications import mailer

    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    d = due_of(t)
    scan_at(seeded, d - timedelta(minutes=100))  # 2 h reminder
    relay(seeded)
    assert "abc" in emails_to(seeded, "TASK_REMINDER_2H")
    clock.freeze(d - timedelta(minutes=90))
    ok(client, as_user, "abc", t["id"], "complete", FINISH | {"no_time_reason": "Tiny change, done immediately"})
    with seeded() as s:
        out = mailer.dispatch_emails(s, d - timedelta(minutes=80))
        s.commit()
        row = s.scalar(select(EmailLog).join(Notification, Notification.id == EmailLog.notification_id).where(Notification.event_type == "TASK_REMINDER_2H"))
    assert out["skipped"] >= 1 and row.status == "skipped"  # the employee is not nagged about work they already finished


def test_reminder_rules_are_seeded_as_specified(db):
    codes = {r.code: (r.kind, r.minutes, r.working_days) for r in db.scalars(select(ReminderRule))}
    assert codes == {
        "before_24h": ("before", 1440, 0), "before_2h": ("before", 120, 0), "at_due": ("at_due", 0, 0),
        "after_1d": ("after_working_days", 0, 1), "after_3d": ("after_working_days", 0, 3), "after_7d": ("after_working_days", 0, 7),
    }  # fmt: skip


_ = service
