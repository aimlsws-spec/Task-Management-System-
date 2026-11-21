"""Phase 5: deadlines are changed only by authorized people, with a reason, and the original is never lost."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.modules.audit.models import ActivityLog
from app.modules.tasks.models import Task, TaskDeadlineHistory

from .helpers import ABC, API, FE, HR1, at, do, eid, make, ok


def later(days: int) -> str:
    return str(date.today() + timedelta(days=days))


REASON = "Client asked for an extra integration"


def change(client, as_user, who, tid, days, reason=REASON):
    body = {"due_date": later(days), "reason": reason}
    return client.post(f"{API}/tasks/{tid}/deadline", headers=as_user(who), json=body)


# ---------------------------------------------------------------- changing a deadline


def test_extending_a_deadline_records_everything_and_keeps_the_original(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(6))
    r = change(client, as_user, "owner", t["id"], 8)
    assert r.status_code == 200, r.text
    d = r.json()["task"]
    assert d["original_due_at"] == t["original_due_at"] and d["due_at"] != t["due_at"]  # the original never moves
    dl = d["deadline"]
    assert dl["version"] == 2 and dl["extension_count"] == 1
    h = dl["history"]
    assert [x["version"] for x in h] == [1, 2] and [x["type"] for x in h] == ["initial", "extension"]
    assert h[1]["previous_due_at"] == t["due_at"] and h[1]["changed_by"] == "Demo Owner" and h[1]["reason"] == REASON and h[1]["at"]


def test_two_extensions_show_original_current_count_and_every_step(client, as_user, seeded):
    """The brief's example: original, first extension, second extension."""
    t = make(client, as_user, seeded, due_date=later(5))
    change(client, as_user, "owner", t["id"], 7, "First extension: waiting on the API vendor")
    d = change(client, as_user, "manager", t["id"], 10, "Second extension: scope grew after review").json()["task"]
    dl = d["deadline"]
    assert dl["extension_count"] == 2 and dl["version"] == 3 and d["extension_count"] == 2
    assert [(x["changed_by"], x["type"]) for x in dl["history"]] == [("Demo Owner", "initial"), ("Demo Owner", "extension"), ("Demo Manager", "extension")]
    assert dl["history"][2]["previous_due_at"] == dl["history"][1]["new_due_at"]
    assert d["original_due_at"] == t["original_due_at"]


def test_shortening_is_allowed_with_a_reason_but_is_not_an_extension(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(9))
    d = change(client, as_user, "owner", t["id"], 4, "Customer launch moved earlier").json()["task"]
    assert d["deadline"]["history"][-1]["type"] == "shorten" and d["deadline"]["extension_count"] == 0 and d["deadline"]["version"] == 2


def test_who_may_change_a_deadline(client, as_user, seeded):
    t = make(client, as_user, seeded, assignee=ABC)  # a Developers task
    for i, who in enumerate(("owner", "ceo", "manager", "devhead")):
        assert change(client, as_user, who, t["id"], 8 + i).status_code == 200, who
    assert change(client, as_user, "abc", t["id"], 20).status_code == 403  # employees can only ask
    assert change(client, as_user, "hrhead", t["id"], 21).status_code == 404  # another department
    assert change(client, as_user, "admin", t["id"], 22).status_code == 403
    hr_task = make(client, as_user, seeded, assignee=HR1)
    assert change(client, as_user, "devhead", hr_task["id"], 9).status_code == 404  # outside their department


def test_deadline_change_validation(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(6))
    assert change(client, as_user, "owner", t["id"], 8, reason="too short").status_code == 422
    r = change(client, as_user, "owner", t["id"], -1)
    assert r.status_code == 422 and r.json()["code"] == "PAST_DEADLINE"
    r = change(client, as_user, "owner", t["id"], 6)  # same date and the same end-of-day time
    assert r.status_code == 422 and r.json()["code"] == "NO_CHANGE"
    r = client.post(f"{API}/tasks/{t['id']}/deadline", headers=as_user("owner"),
                    json={"due_date": later(8), "reason": REASON, "original_due_at": "2020-01-01T00:00:00Z"})  # fmt: skip
    assert r.status_code == 422  # no way to send or overwrite the original


def test_closed_tasks_keep_their_deadline(client, as_user, seeded):
    t = make(client, as_user, seeded)
    ok(client, as_user, "owner", t["id"], "cancel", {"reason": "No longer needed"})
    r = change(client, as_user, "owner", t["id"], 9)
    assert r.status_code == 409 and r.json()["code"] == "TASK_CLOSED"


def test_a_deadline_on_a_day_off_warns(client, as_user, seeded):
    t = make(client, as_user, seeded)
    d = date.today() + timedelta(days=8)
    while d.weekday() != 6:
        d += timedelta(days=1)
    r = client.post(f"{API}/tasks/{t['id']}/deadline", headers=as_user("owner"), json={"due_date": str(d), "reason": REASON})
    assert r.status_code == 200 and any("falls on" in w for w in r.json()["warnings"])


def test_history_endpoint_and_audit_trail(client, as_user, seeded):
    t = make(client, as_user, seeded)
    change(client, as_user, "owner", t["id"], 9)
    h = client.get(f"{API}/tasks/{t['id']}/deadline-history", headers=as_user("abc")).json()  # the assignee sees it too
    assert len(h) == 2 and h[1]["changed_by"] == "Demo Owner"
    assert client.get(f"{API}/tasks/{t['id']}/deadline-history", headers=as_user("hrhead")).status_code == 404
    actions = [e["action"] for e in client.get(f"{API}/tasks/{t['id']}/timeline", headers=as_user("owner")).json()]
    assert actions[-1] == "TASK_DEADLINE_CHANGED"
    with seeded() as s:
        log = s.scalar(select(ActivityLog).where(ActivityLog.action == "TASK_DEADLINE_CHANGED"))
        assert log.after_json["reason"] == REASON and log.after_json["version"] == 2 and log.before_json["due_at"] == t["due_at"]


def test_the_original_deadline_cannot_be_changed_by_any_code_path(client, as_user, seeded):
    t = make(client, as_user, seeded)
    with seeded() as s:
        task = s.get(Task, t["id"])
        task.original_due_at = task.original_due_at + timedelta(days=3)
        with pytest.raises(RuntimeError, match="immutable"):
            s.flush()
        s.rollback()
        # ...while the normal deadline can change
        task = s.get(Task, t["id"])
        task.due_at = task.due_at + timedelta(days=3)
        s.flush()
        assert s.scalar(select(TaskDeadlineHistory.new_due_at).where(TaskDeadlineHistory.task_id == t["id"])) == task.original_due_at


# ---------------------------------------------------------------- extension requests (employee asks, manager decides)


def ask(client, as_user, tid, days=9, reason="The vendor API access arrived late", who="abc"):
    return client.post(f"{API}/tasks/{tid}/extension-requests", headers=as_user(who), json={"due_date": later(days), "reason": reason})


def test_employee_requests_and_manager_approves(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(5))
    r = ask(client, as_user, t["id"], 8)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()["due_at"] == t["due_at"]  # nothing moves yet
    queue = client.get(f"{API}/extension-requests", headers=as_user("devhead")).json()
    assert [q["task_no"] for q in queue] == [t["task_no"]] and queue[0]["assignee"] == "ABC"
    rid = queue[0]["id"]
    assert client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("abc"), json={"decision": "approve"}).status_code == 403
    assert client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("hrhead"), json={"decision": "approve"}).status_code == 404
    done = client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("devhead"), json={"decision": "approve", "note": "Fair"}).json()
    assert done["request"]["status"] == "approved" and done["request"]["decided_by"] == "Developers Head"
    d = client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()
    assert d["deadline"]["extension_count"] == 1 and d["deadline"]["history"][-1]["reason"].startswith("Extension approved: The vendor")
    assert client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("devhead"), json={"decision": "approve"}).status_code == 409


def test_manager_can_approve_a_different_date(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(5))
    rid = ask(client, as_user, t["id"], 12).json()["id"]
    body = {"decision": "approve", "due_date": later(8)}
    r = client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("owner"), json=body).json()
    assert r["request"]["approved_due_at"].startswith(later(8)) and r["request"]["requested_due_at"].startswith(later(12))


def test_declining_needs_a_note_and_changes_nothing(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(5))
    rid = ask(client, as_user, t["id"], 9).json()["id"]
    assert client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("manager"), json={"decision": "reject"}).status_code == 422
    r = client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("manager"), json={"decision": "reject", "note": "Deadline is fixed by the client"})
    assert r.json()["request"]["status"] == "rejected"
    d = client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()
    assert d["extension_count"] == 0 and d["due_at"] == t["due_at"]
    assert ask(client, as_user, t["id"], 9).status_code == 201  # they may ask again


def test_extension_request_rules(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(5))
    assert ask(client, as_user, t["id"], 3).json()["code"] == "NOT_LATER"  # must be later than now due
    assert ask(client, as_user, t["id"], 9, reason="short").status_code == 422
    assert ask(client, as_user, t["id"], 9, who="owner").status_code == 403  # only the assignee asks
    assert ask(client, as_user, t["id"], 9).status_code == 201
    assert ask(client, as_user, t["id"], 10).json()["code"] == "REQUEST_PENDING"  # one at a time


def test_nobody_decides_their_own_extension_request(client, as_user, seeded):
    t = make(client, as_user, seeded, assignee="EMP-0004", due_date=later(5))  # a task for the Developers Head
    rid = ask(client, as_user, t["id"], 9, who="devhead").json()["id"]
    assert client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("devhead"), json={"decision": "approve"}).status_code == 403
    assert client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("manager"), json={"decision": "approve"}).status_code == 200
    assert client.get(f"{API}/extension-requests", headers=as_user("hrhead")).json() == []


def test_a_request_that_became_stale_cannot_be_approved(client, as_user, seeded):
    t = make(client, as_user, seeded, due_date=later(5))
    rid = ask(client, as_user, t["id"], 8).json()["id"]
    change(client, as_user, "owner", t["id"], 12)  # a manager already moved it beyond what was asked
    r = client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("manager"), json={"decision": "approve"})
    assert r.status_code == 409 and r.json()["code"] == "STALE_REQUEST"  # it would move the deadline EARLIER
    again = client.post(f"{API}/extension-requests/{rid}/decision", headers=as_user("manager"), json={"decision": "approve", "due_date": later(15)})
    assert again.status_code == 200  # approving a genuinely later date is fine


# ---------------------------------------------------------------- statistics


def test_extension_statistics_follow_scope(client, as_user, seeded):
    a, f = make(client, as_user, seeded, assignee=ABC, due_date=later(5)), make(client, as_user, seeded, assignee=FE, due_date=later(5))
    for days in (7, 9, 11):
        change(client, as_user, "owner", a["id"], days, f"Extension to day {days} for the client")
    change(client, as_user, "owner", f["id"], 8, "One extension for the frontend work")
    s = client.get(f"{API}/stats/deadlines", headers=as_user("owner")).json()
    assert s["tasks_extended"] == 2 and s["extensions_total"] == 4
    assert s["most_extended"][0]["task_no"] == a["task_no"] and s["most_extended"][0]["extensions"] == 3
    assert s["by_assignee"][0] == {"employee_id": eid(seeded, ABC), "full_name": "ABC", "extensions": 3, "tasks": 1}
    assert client.get(f"{API}/stats/deadlines", headers=as_user("hrhead")).json()["extensions_total"] == 0  # another department
    assert client.get(f"{API}/stats/deadlines", headers=as_user("abc")).json()["extensions_total"] == 3  # their own tasks only
    assert client.get(f"{API}/stats/deadlines", headers=as_user("admin")).status_code == 403


def test_version_bumps_so_old_reminder_schedules_can_never_apply(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    v1 = client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["deadline"]["version"]
    change(client, as_user, "owner", t["id"], 9)
    v2 = client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["deadline"]["version"]
    assert (v1, v2) == (1, 2)  # Phase 6 reminders are keyed on this version
    _ = do
