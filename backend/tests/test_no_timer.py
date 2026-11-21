"""Time tracking is switched off in the product (TMS_TIME_TRACKING=false, the default): only deadlines matter.
The rest of the suite switches it on (conftest) because the timer engine is still there and still tested."""

import pytest

from app.core.config import get_settings

from .helpers import ABC, API, FINISH, eid, make, ok


@pytest.fixture(autouse=True)
def timer_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "time_tracking", False)


def test_start_moves_the_task_to_in_progress_without_a_timer(client, as_user, seeded):
    t = make(client, as_user, seeded)
    d = ok(client, as_user, "abc", t["id"], "start")
    assert d["status"] == "in_progress" and d["timer_running"] is False
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"] is None
    from sqlalchemy import select

    from app.modules.timetracking.models import TimeLog

    with seeded() as s:
        assert s.scalar(select(TimeLog.id)) is None  # nothing was recorded


def test_no_timer_buttons_are_offered(client, as_user, seeded):
    t = make(client, as_user, seeded)
    assert "start" in client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()["allowed_actions"]
    ok(client, as_user, "abc", t["id"], "start")
    acts = client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()["allowed_actions"]
    assert not {"start", "pause", "stop"} & set(acts) and "complete" in acts


@pytest.mark.parametrize("action", ["pause", "stop"])
def test_pause_and_stop_are_refused(client, as_user, seeded, action):
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    r = client.post(f"{API}/tasks/{t['id']}/{action}", headers=as_user("abc"), json={})
    assert r.status_code == 409 and r.json()["code"] == "TIMER_DISABLED"


def test_completing_never_asks_for_time(client, as_user, seeded):
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    d = ok(client, as_user, "abc", t["id"], "complete", FINISH)  # no "no_time_reason"
    assert d["status"] == "under_review"  # finished (ADR 008: reviewed before it is Completed)


def test_first_start_still_tells_the_assigner(client, as_user, seeded):
    from tests.test_notifications import relay

    t = make(client, as_user, seeded, assignee=ABC)
    ok(client, as_user, "abc", t["id"], "start")
    relay(seeded)
    items = client.get(f"{API}/notifications", headers=as_user("owner")).json()["items"]
    assert [n for n in items if n["event_type"] == "TASK_STARTED"]
    assert eid(seeded, ABC)
