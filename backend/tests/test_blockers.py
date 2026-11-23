"""Phase 7: blockers stop the clock honestly, are tracked end to end, and reach the right people."""

import pytest

from .helpers import ABC, API, FE, FINISH, at, do, eid, make, ok
from .test_notifications import by_user, emails_to, relay

BODY = {
    "blocker_type": "technical", "title": "API credentials missing",
    "description": "Authentication fails because the credentials were never issued to us.",
    "impact": "Development is blocked", "blocks_work": True, "expected_resolution": "Waiting for API credentials",
}  # fmt: skip


def raise_b(client, as_user, tid, who="abc", **over):
    return client.post(f"{API}/tasks/{tid}/blockers", headers=as_user(who), json=BODY | over)


def act(client, as_user, who, bid, action, **body):
    return client.post(f"{API}/blockers/{bid}/{action}", headers=as_user(who), json=body)


def task(client, as_user, tid, who="abc"):
    return client.get(f"{API}/tasks/{tid}", headers=as_user(who)).json()


def started(client, as_user, seeded, **over):
    at(0)
    t = make(client, as_user, seeded, **over)
    ok(client, as_user, "abc", t["id"], "start")
    return t


# ---------------------------------------------------------------- raising a blocker blocks the work


def test_raising_a_blocker_blocks_the_task_and_stops_the_timer(client, as_user, seeded):
    t = started(client, as_user, seeded)
    at(60)
    r = raise_b(client, as_user, t["id"])
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "open" and b["blocks_work"] and b["raised_by"] == "ABC" and b["events"][0]["event"] == "created"
    d = task(client, as_user, t["id"])
    assert d["status"] == "blocked" and d["timer_running"] is False and d["open_blockers"] == 1
    assert d["time"]["active_seconds"] == 3600  # the clock stopped at the moment of blocking
    assert d["time"]["sessions"][0]["end_reason"] == "blocked"
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"] is None
    assert "start" not in d["allowed_actions"] and "raise_blocker" in d["allowed_actions"]
    r = do(client, as_user, "abc", t["id"], "start")
    assert r.status_code == 409 and r.json()["code"] == "TASK_NOT_STARTABLE"  # cannot work a blocked task


def test_a_non_blocking_issue_changes_nothing_about_the_work(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"], blocks_work=False, title="Docs are outdated").json()
    d = task(client, as_user, t["id"])
    assert d["status"] == "in_progress" and d["timer_running"] is True and d["open_blockers"] == 1
    assert act(client, as_user, "devhead", b["id"], "resolve", note="Docs updated").status_code == 200
    assert task(client, as_user, t["id"])["status"] == "in_progress"  # nothing to restore


def test_waiting_time_is_reported_apart_from_working_time(client, as_user, seeded):
    t = started(client, as_user, seeded)
    at(60)  # 1 h of real work
    b = raise_b(client, as_user, t["id"]).json()
    at(300)  # 4 h waiting for credentials
    assert act(client, as_user, "devhead", b["id"], "resolve", note="Credentials issued by the vendor").status_code == 200
    tm = task(client, as_user, t["id"])["time"]
    assert tm["active_seconds"] == 3600 and tm["blocked_seconds"] == 4 * 3600  # 1 h worked, 4 h blocked: never mixed
    assert tm["elapsed_seconds"] == 300 * 60


def test_overlapping_blockers_count_blocked_time_once(client, as_user, seeded):
    t = started(client, as_user, seeded)
    at(60)
    b1 = raise_b(client, as_user, t["id"], title="First problem").json()
    at(120)
    b2 = raise_b(client, as_user, t["id"], title="Second problem").json()
    at(180)
    act(client, as_user, "devhead", b1["id"], "resolve", note="First one fixed")
    assert task(client, as_user, t["id"])["status"] == "blocked"  # the second still blocks
    at(240)
    act(client, as_user, "devhead", b2["id"], "resolve", note="Second one fixed")
    d = task(client, as_user, t["id"])
    assert d["status"] == "in_progress" and d["time"]["blocked_seconds"] == 3 * 3600  # 60 -> 240 min, not 4 h


def test_clearing_the_last_blocker_restores_the_previous_status(client, as_user, seeded):
    at(0)
    fresh = make(client, as_user, seeded)  # never started: "assigned"
    b = raise_b(client, as_user, fresh["id"]).json()
    assert task(client, as_user, fresh["id"])["status"] == "blocked"
    act(client, as_user, "devhead", b["id"], "resolve", note="Access granted")
    assert task(client, as_user, fresh["id"])["status"] == "assigned"
    held = make(client, as_user, seeded, title="Held task")
    ok(client, as_user, "abc", held["id"], "start")
    ok(client, as_user, "abc", held["id"], "hold", {"reason": "Waiting for the client"})
    b2 = raise_b(client, as_user, held["id"], title="Also missing data").json()
    act(client, as_user, "manager", b2["id"], "resolve", note="Data delivered")
    assert task(client, as_user, held["id"])["status"] == "on_hold"  # back to exactly where it was


def test_the_history_of_a_blocker_is_complete(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    act(client, as_user, "devhead", b["id"], "acknowledge")
    act(client, as_user, "devhead", b["id"], "assign", owner_employee_id=eid(seeded, FE), note="You have the vendor contact")
    act(client, as_user, "frontend", b["id"], "reply", note="Asked the vendor, answer expected tomorrow")
    act(client, as_user, "devhead", b["id"], "escalate", note="Vendor is not responding")
    act(client, as_user, "frontend", b["id"], "resolve", note="Credentials received")
    act(client, as_user, "abc", b["id"], "close", note="Confirmed, thanks")
    full = client.get(f"{API}/blockers/{b['id']}", headers=as_user("owner")).json()
    assert [e["event"] for e in full["events"]] == ["created", "acknowledged", "assigned", "replied", "escalated", "resolved", "closed"]
    assert [e["by"] for e in full["events"]][:3] == ["ABC", "Developers Head", "Developers Head"]
    assert full["status"] == "closed" and full["owner"] == "Frontend Dev" and full["resolution_note"] == "Credentials received"
    assert [e["to"] for e in full["events"] if e["event"] in ("acknowledged", "assigned", "resolved", "closed")] == ["acknowledged", "in_progress", "resolved", "closed"]


# ---------------------------------------------------------------- who may do what


def test_only_the_assignee_raises_and_only_on_open_work(client, as_user, seeded):
    t = started(client, as_user, seeded)
    assert raise_b(client, as_user, t["id"], who="devhead").status_code == 403  # a manager cannot report it for them
    assert raise_b(client, as_user, t["id"], who="hrhead").status_code == 404
    assert raise_b(client, as_user, t["id"], who="admin").status_code == 403
    at(30)
    ok(client, as_user, "abc", t["id"], "submit-for-review", FINISH)
    r = raise_b(client, as_user, t["id"])
    assert r.status_code == 409 and r.json()["code"] == "TASK_NOT_BLOCKABLE"  # waiting for review


def test_manager_actions_need_authority_over_the_employee(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    for action, body in (("acknowledge", {}), ("assign", {"owner_employee_id": eid(seeded, FE)}), ("escalate", {"note": "Please look"}), ("resolve", {"note": "Fixed it myself"})):
        assert act(client, as_user, "abc", b["id"], action, **body).status_code == 403, action  # the employee cannot do management's part
    assert act(client, as_user, "hrhead", b["id"], "acknowledge").status_code == 404  # another department cannot even see it
    assert act(client, as_user, "admin", b["id"], "acknowledge").status_code == 403
    assert act(client, as_user, "devhead", b["id"], "assign", owner_employee_id=eid(seeded, "EMP-0009")).status_code == 404  # HR is outside their scope
    assert act(client, as_user, "devhead", b["id"], "acknowledge").json()["status"] == "acknowledged"
    assert act(client, as_user, "devhead", b["id"], "acknowledge").status_code == 409


def test_the_person_it_was_assigned_to_can_work_and_resolve_it(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    act(client, as_user, "devhead", b["id"], "assign", owner_employee_id=eid(seeded, FE))
    assert act(client, as_user, "frontend", b["id"], "start").status_code == 409  # assignment already moved it to in progress
    assert act(client, as_user, "frontend", b["id"], "resolve", note="x").status_code == 422
    assert act(client, as_user, "frontend", b["id"], "resolve", note="Credentials received").json()["status"] == "resolved"
    assert act(client, as_user, "frontend", b["id"], "resolve", note="Again please").status_code == 409


def test_employee_confirms_or_reopens_and_the_task_blocks_again(client, as_user, seeded):
    t = started(client, as_user, seeded)
    at(60)
    b = raise_b(client, as_user, t["id"]).json()
    act(client, as_user, "devhead", b["id"], "resolve", note="Credentials issued")
    assert task(client, as_user, t["id"])["status"] == "in_progress"
    assert act(client, as_user, "abc", b["id"], "reopen").status_code == 422  # must say why
    r = act(client, as_user, "abc", b["id"], "reopen", note="The credentials do not work either")
    assert r.status_code == 200 and r.json()["status"] == "open"
    assert task(client, as_user, t["id"])["status"] == "blocked"  # blocked again
    act(client, as_user, "devhead", b["id"], "resolve", note="New credentials sent")
    assert act(client, as_user, "abc", b["id"], "close", note="Works now").json()["status"] == "closed"
    assert act(client, as_user, "abc", b["id"], "close").status_code == 409


def test_an_employee_can_withdraw_their_own_blocker(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    r = act(client, as_user, "abc", b["id"], "close", note="Found the credentials myself")
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert task(client, as_user, t["id"])["status"] == "in_progress"  # nothing blocks any more


def test_a_blocked_task_cannot_be_completed(client, as_user, seeded):
    t = started(client, as_user, seeded)
    at(30)
    raise_b(client, as_user, t["id"])
    r = do(client, as_user, "abc", t["id"], "complete", FINISH)
    assert r.status_code == 409  # a blocked task is not finished work


def test_cancelling_a_task_closes_its_blockers(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    ok(client, as_user, "owner", t["id"], "cancel", {"reason": "No longer needed by the client"})
    full = client.get(f"{API}/blockers/{b['id']}", headers=as_user("owner")).json()
    assert full["status"] == "closed" and full["events"][-1]["note"] == "Task cancelled"


def test_reassigning_a_blocked_task_keeps_it_blocked_for_the_new_owner(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    ok(client, as_user, "devhead", t["id"], "reassign", {"assignee_id": eid(seeded, FE), "reason": "ABC is on leave"})
    assert task(client, as_user, t["id"], "frontend")["status"] == "blocked"
    act(client, as_user, "devhead", b["id"], "resolve", note="Credentials issued")
    assert task(client, as_user, t["id"], "frontend")["status"] == "assigned"  # the new owner starts fresh


def test_blocker_validation(client, as_user, seeded):
    t = started(client, as_user, seeded)
    assert raise_b(client, as_user, t["id"], blocker_type="mystery").status_code == 422
    assert raise_b(client, as_user, t["id"], title="x").status_code == 422
    assert raise_b(client, as_user, t["id"], description="bad").status_code == 422
    assert raise_b(client, as_user, t["id"], attachment_id=999999).json()["code"] == "INVALID_ATTACHMENT"
    assert raise_b(client, as_user, t["id"], raised_by_user_id=1).status_code == 422  # no mass assignment


# ---------------------------------------------------------------- the manager's queue


def test_blocker_queue_is_scoped(client, as_user, seeded):
    a = started(client, as_user, seeded)
    h = make(client, as_user, seeded, assignee="EMP-0009", title="HR task")
    ok(client, as_user, "hr1", h["id"], "start")
    b1 = raise_b(client, as_user, a["id"]).json()
    raise_b(client, as_user, h["id"], who="hr1", title="HR blocker")
    titles = lambda who, **q: {b["title"] for b in client.get(f"{API}/blockers", params=q, headers=as_user(who)).json()["items"]}  # noqa: E731
    # Line heads and manager see their open blockers; Owner/CEO do not see un-escalated blockers when a head exists
    assert titles("devhead") == {"API credentials missing"} and titles("hrhead") == {"HR blocker"}
    assert titles("manager") == {"API credentials missing", "HR blocker"}
    assert titles("owner") == set() and titles("ceo") == set()  # not escalated yet
    assert titles("abc") == {"API credentials missing"}  # employees see their own
    assert titles("frontend") == set()
    assert client.get(f"{API}/blockers", headers=as_user("admin")).status_code == 403
    item = client.get(f"{API}/blockers", headers=as_user("devhead")).json()["items"][0]
    assert {"acknowledge", "assign", "resolve", "escalate", "reply"} <= set(item["actions"]) and item["assignee"] == "ABC"
    b = item["id"]
    # When head escalates to CEO / Owner, it appears in owner and ceo panel
    act(client, as_user, "devhead", b, "escalate", note="Need CEO/Owner approval for license")
    assert titles("owner") == {"API credentials missing"} and titles("ceo") == {"API credentials missing"}
    act(client, as_user, "devhead", b, "resolve", note="Fixed")
    assert titles("devhead") == set()  # open ones only by default
    assert titles("devhead", status="resolved") == {"API credentials missing"}


# ---------------------------------------------------------------- who is told


def test_a_blocker_tells_the_management_line_and_confirms_to_the_employee(client, as_user, seeded):
    t = started(client, as_user, seeded)
    raise_b(client, as_user, t["id"])
    relay(seeded)
    got = by_user(seeded, "BLOCKER_RAISED")
    # Head and Manager are in the loop; Owner and CEO are not told directly when a head exists
    assert set(got) == {"abc", "devhead", "manager"}
    assert "owner" not in got and "ceo" not in got
    assert got["devhead"][0].urgent and "Work is stopped" in got["devhead"][0].body
    assert sorted(emails_to(seeded, "BLOCKER_RAISED")) == ["devhead", "manager"]


def test_a_critical_task_blocker_also_reaches_the_ceo(client, as_user, seeded):
    # When task has no head (neither explicit nor department fallback), blocker routes directly to CEO and Owner
    t = started(client, as_user, seeded, priority="critical")
    from app.modules.org.models import Department, DepartmentHead
    from app.modules.tasks.models import Task, TaskHead
    with seeded() as db:
        task_row = db.get(Task, t["id"])
        task_row.head_employee_id = None
        task_row.sub_head_employee_id = None
        db.query(TaskHead).filter(TaskHead.task_id == t["id"]).delete()
        if task_row.department_id:
            dept = db.get(Department, task_row.department_id)
            if dept:
                dept.head_employee_id = None
                dept.sub_head_employee_id = None
            db.query(DepartmentHead).filter(DepartmentHead.department_id == task_row.department_id).delete()
        db.commit()
    raise_b(client, as_user, t["id"])
    relay(seeded)
    assert "ceo" in by_user(seeded, "BLOCKER_RAISED")
    assert "owner" in by_user(seeded, "BLOCKER_RAISED")


def test_resolution_reaches_the_employee_and_the_manager(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    act(client, as_user, "devhead", b["id"], "acknowledge")
    act(client, as_user, "devhead", b["id"], "resolve", note="Credentials issued by the vendor")
    relay(seeded)
    assert set(by_user(seeded, "BLOCKER_ACKNOWLEDGED")) == {"abc"}
    res = by_user(seeded, "BLOCKER_RESOLVED")
    assert set(res) == {"abc", "owner"} and "Credentials issued by the vendor" in res["abc"][0].body  # devhead did it
    assert "abc" in emails_to(seeded, "BLOCKER_RESOLVED")


def test_escalation_reaches_the_top(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    act(client, as_user, "devhead", b["id"], "escalate", note="The vendor has not replied for three days")
    relay(seeded)
    got = by_user(seeded, "BLOCKER_ESCALATED")
    assert {"manager", "ceo", "owner", "abc"} <= set(got) and "devhead" not in got  # the escalator is not told about their own action


def test_assignment_and_replies_notify_the_right_person(client, as_user, seeded):
    t = started(client, as_user, seeded)
    b = raise_b(client, as_user, t["id"]).json()
    act(client, as_user, "devhead", b["id"], "assign", owner_employee_id=eid(seeded, FE), note="You know the vendor")
    act(client, as_user, "frontend", b["id"], "reply", note="Emailed them, waiting")
    relay(seeded)
    assert set(by_user(seeded, "BLOCKER_ASSIGNED")) == {"frontend", "abc"}
    rep = by_user(seeded, "BLOCKER_REPLIED")
    assert set(rep) == {"abc", "devhead", "owner"} and "frontend" not in rep  # the raiser, the manager and the rest of the loop, not the replier


_ = pytest, ABC
