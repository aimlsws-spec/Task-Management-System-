"""A task is not late until 40 minutes after its deadline (TMS_OVERDUE_GRACE_MINUTES). After that the employee must give a reason."""

from datetime import timedelta

import pytest

from app.core import clock
from app.core.config import get_settings
from app.modules.notifications import reminders

from .helpers import API, BASE, at, make, ok

DUE_AT_MIN = 540  # a deadline is a date: it falls at 18:30 IST (end of day), which is BASE (09:30 IST) + 540 minutes
FINISH = {"summary": "Finished the requested change.", "tested": True, "no_time_reason": "Quick change, done in minutes"}


@pytest.fixture(autouse=True)
def grace_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "overdue_grace_minutes", 40)


def start_task(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, due_date=str(BASE.date()))
    at(10)
    ok(client, as_user, "abc", t["id"], "start")
    return t


def task(client, as_user, tid, who="abc"):
    return client.get(f"{API}/tasks/{tid}", headers=as_user(who)).json()


def test_a_few_minutes_after_the_deadline_is_not_late(client, as_user, seeded):
    t = start_task(client, as_user, seeded)
    at(DUE_AT_MIN + 3)  # 3 minutes past
    d = task(client, as_user, t["id"])
    assert d["is_overdue"] is False and d["delay"]["required"] is False
    done = ok(client, as_user, "abc", t["id"], "complete", FINISH)  # no explanation asked for
    assert done["status"] == "under_review"  # finished: now in review (ADR 008)


def test_the_last_minute_of_the_grace_period_is_still_fine(client, as_user, seeded):
    t = start_task(client, as_user, seeded)
    at(DUE_AT_MIN + 39)
    assert ok(client, as_user, "abc", t["id"], "complete", FINISH)["status"] == "under_review"


def test_after_the_grace_period_a_reason_is_required(client, as_user, seeded):
    t = start_task(client, as_user, seeded)
    at(DUE_AT_MIN + 41)
    d = task(client, as_user, t["id"])
    assert d["is_overdue"] is True and d["delay"]["required"] is True
    r = client.post(f"{API}/tasks/{t['id']}/complete", headers=as_user("abc"), json=FINISH)
    assert r.status_code == 409 and r.json()["code"] == "DELAY_EXPLANATION_REQUIRED"
    done = ok(client, as_user, "abc", t["id"], "complete", FINISH | {"late_reason": "The client changed the design twice"})
    assert done["status"] == "under_review"


def test_overdue_list_and_counts_wait_for_the_grace_period(client, as_user, seeded):
    t = start_task(client, as_user, seeded)
    ids = lambda: {x["id"] for x in client.get(f"{API}/tasks", headers=as_user("owner"), params={"overdue": "true"}).json()["items"]}  # noqa: E731
    at(DUE_AT_MIN + 30)
    assert t["id"] not in ids()
    at(DUE_AT_MIN + 45)
    assert t["id"] in ids()


def test_overdue_emails_wait_for_the_grace_period(client, as_user, seeded):
    start_task(client, as_user, seeded)

    def fired(minutes):
        now = at(minutes)
        with seeded() as s:
            out = reminders.scan(s, now)
            s.commit()
        return out

    assert "at_due" not in fired(DUE_AT_MIN + 5)
    assert "at_due" in fired(DUE_AT_MIN + 41)
    assert clock.utcnow() > BASE + timedelta(minutes=DUE_AT_MIN)
