"""Phase 3: assigning tasks, who sees what, the status workflow, workload per person, projects, attachments."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.modules.audit.models import ActivityLog
from app.modules.org.models import Employee
from app.modules.tasks.models import Task, TaskAssignment, TaskDeadlineHistory, TaskStatusHistory

API = "/api/v1"


def eid(seeded, code):
    with seeded() as s:
        return s.scalar(select(Employee.id).where(Employee.employee_code == code))


ABC, FE, DEVHEAD, HRHEAD, HR1, MANAGER, CEO, OWNER, ADMIN, SUPPORT = (
    "EMP-0007", "EMP-0008", "EMP-0004", "EMP-0005", "EMP-0009", "EMP-0003", "EMP-0002", "EMP-0001", "EMP-0000", "EMP-0011",
)  # fmt: skip


def body(seeded, assignee=ABC, **over):
    return {
        "title": "Develop AI Chatbot API", "description": "Develop and integrate the chatbot API.",
        "assignee_id": eid(seeded, assignee), "priority": "high",
        "due_date": str(date.today() + timedelta(days=5)), "estimated_hours": 12,
    } | over  # fmt: skip


def make(client, as_user, seeded, who="owner", assignee=ABC, **over):
    r = client.post(f"{API}/tasks", headers=as_user(who), json=body(seeded, assignee, **over))
    assert r.status_code == 201, r.text
    return r.json()["task"]


# ---------------------------------------------------------------- assigning


def test_owner_assigns_task_to_ai_ml_developer(client, as_user, seeded):
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json=body(seeded, priority="high"))
    assert r.status_code == 201, r.text
    t = r.json()["task"]
    assert t["task_no"].startswith("TSK-") and t["status"] == "assigned" and t["priority"] == "high"
    assert t["assignee"]["full_name"] == "ABC" and t["assigned_by"]["full_name"] == "Demo Owner"
    assert t["original_due_at"] == t["due_at"] and t["estimated_hours"] == 12
    assert t["department_id"] == t["assignee"]["department_id"]  # department follows the assignee


def test_creation_is_fully_tracked(client, as_user, seeded):
    t = make(client, as_user, seeded)
    with seeded() as s:
        assert s.scalar(select(TaskAssignment).where(TaskAssignment.task_id == t["id"]))
        hist = s.scalars(select(TaskStatusHistory).where(TaskStatusHistory.task_id == t["id"])).all()
        assert [(h.from_status, h.to_status) for h in hist] == [(None, "assigned")]
        dl = s.scalar(select(TaskDeadlineHistory).where(TaskDeadlineHistory.task_id == t["id"]))
        assert dl.deadline_version == 1 and dl.change_type == "initial" and dl.previous_due_at is None
        log = s.scalar(select(ActivityLog).where(ActivityLog.task_id == t["id"], ActivityLog.action == "TASK_CREATED"))
        assert log.after_json["assignee_id"] == eid(seeded, ABC)


@pytest.mark.parametrize("who,assignee", [
    ("owner", ABC), ("owner", CEO), ("ceo", ABC), ("ceo", MANAGER), ("manager", DEVHEAD), ("manager", ABC),
    ("manager", SUPPORT), ("devhead", ABC), ("devhead", FE),
])  # fmt: skip
def test_allowed_assignments(client, as_user, seeded, who, assignee):
    assert client.post(f"{API}/tasks", headers=as_user(who), json=body(seeded, assignee)).status_code == 201


@pytest.mark.parametrize("who,assignee,codes", [
    ("ceo", OWNER, {403}),  # upward: the Owner outranks the CEO
    ("manager", CEO, {404}),  # outside the Manager's team
    ("devhead", HR1, {404}),  # another department
    ("devhead", MANAGER, {404}),  # upward and outside scope
    ("owner", ADMIN, {422}),  # the Admin never receives tasks
    ("owner", OWNER, {422}),  # no self-assignment
])  # fmt: skip
def test_forbidden_assignments(client, as_user, seeded, who, assignee, codes):
    assert client.post(f"{API}/tasks", headers=as_user(who), json=body(seeded, assignee)).status_code in codes


@pytest.mark.parametrize("who", ["abc", "admin"])
def test_employees_and_admin_cannot_create_tasks(client, as_user, seeded, who):
    assert client.post(f"{API}/tasks", headers=as_user(who), json=body(seeded)).status_code == 403


def test_cannot_assign_to_inactive_employee(client, as_user, seeded):
    client.post(f"{API}/employees/{eid(seeded, ABC)}/deactivate", headers=as_user("admin"))
    assert client.post(f"{API}/tasks", headers=as_user("owner"), json=body(seeded)).status_code == 422


def test_validation(client, as_user, seeded):
    h = as_user("owner")
    past = str(date.today() - timedelta(days=1))
    assert client.post(f"{API}/tasks", headers=h, json=body(seeded, due_date=past)).json()["code"] == "PAST_DEADLINE"
    assert client.post(f"{API}/tasks", headers=h, json=body(seeded, estimated_hours=0)).status_code == 422
    assert client.post(f"{API}/tasks", headers=h, json=body(seeded, priority="urgent")).status_code == 422
    assert client.post(f"{API}/tasks", headers=h, json=body(seeded, title="x")).status_code == 422
    assert client.post(f"{API}/tasks", headers=h, json=body(seeded, project_id=999999)).json()["code"] == "INVALID_REFERENCE"
    late_start = str(date.today() + timedelta(days=9))
    assert client.post(f"{API}/tasks", headers=h, json=body(seeded, start_date=late_start)).json()["code"] == "INVALID_START_DATE"
    assert client.post(f"{API}/tasks", headers=h, json=body(seeded) | {"assigned_by_id": 1}).status_code == 422  # mass assignment


def test_date_only_deadline_means_end_of_day_company_time(client, as_user, seeded):
    d = date.today() + timedelta(days=3)
    t = make(client, as_user, seeded, due_date=str(d))
    assert t["due_at"] == f"{d}T13:00:00Z"  # 18:30 Asia/Kolkata == 13:00 UTC
    # there is no deadline time any more: a client that still sends one is told so instead of being silently ignored
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json=body(seeded, due_date=str(d)) | {"due_time": "10:00"})
    assert r.status_code == 422


def test_deadline_on_a_non_working_day_warns_but_is_allowed(client, as_user, seeded):
    d = date.today() + timedelta(days=1)
    while d.weekday() != 6:  # next Sunday: always off
        d += timedelta(days=1)
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json=body(seeded, due_date=str(d)))
    assert r.status_code == 201 and any("falls on" in w for w in r.json()["warnings"])


# ---------------------------------------------------------------- who sees what


def ids(resp):
    return {t["id"] for t in resp.json()["items"]}


def test_visibility_follows_the_hierarchy(client, as_user, seeded):
    t = make(client, as_user, seeded)  # Owner -> ABC (Developers)
    mine = lambda who: ids(client.get(f"{API}/tasks", headers=as_user(who)))  # noqa: E731
    for who in ("owner", "ceo", "manager", "devhead", "abc"):
        assert t["id"] in mine(who), who  # the loop: assignee, their head, the Manager, CEO and Owner all see it
    assert t["id"] not in mine("hrhead")  # other department
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("hrhead")).status_code == 404
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("support1")).status_code == 404


def test_employee_sees_only_their_own_tasks(client, as_user, seeded):
    mine = make(client, as_user, seeded, assignee=ABC)
    other = make(client, as_user, seeded, assignee=FE)
    got = ids(client.get(f"{API}/tasks", headers=as_user("abc")))
    assert mine["id"] in got and other["id"] not in got
    assert client.get(f"{API}/tasks/{other['id']}", headers=as_user("abc")).status_code == 404


def test_creator_keeps_visibility_of_what_they_assigned(client, as_user, seeded):
    t = make(client, as_user, seeded, who="devhead", assignee=FE)
    assert t["id"] in ids(client.get(f"{API}/tasks", headers=as_user("devhead")))


def test_admin_has_no_access_to_tasks(client, as_user, seeded):
    make(client, as_user, seeded)
    assert client.get(f"{API}/tasks", headers=as_user("admin")).status_code == 403


def test_list_filters_and_priority_engine_order(client, as_user, seeded):
    low = make(client, as_user, seeded, title="Docs", priority="low")
    crit = make(client, as_user, seeded, title="Hotfix", priority="critical")
    high = make(client, as_user, seeded, title="API", priority="high")
    got = client.get(f"{API}/tasks", headers=as_user("abc")).json()["items"]
    assert [t["id"] for t in got] == [crit["id"], high["id"], low["id"]]  # critical first
    h = as_user("owner")
    assert ids(client.get(f"{API}/tasks", params={"priority": "low"}, headers=h)) == {low["id"]}
    assert ids(client.get(f"{API}/tasks", params={"q": "Hotfix"}, headers=h)) == {crit["id"]}
    assert ids(client.get(f"{API}/tasks", params={"assignee_id": eid(seeded, FE)}, headers=h)) == set()
    assert client.get(f"{API}/tasks", params={"mine": True}, headers=as_user("abc")).json()["total"] == 3


def test_overdue_tasks_are_flagged_and_listed_first(client, as_user, seeded):
    t = make(client, as_user, seeded, priority="low")
    later = make(client, as_user, seeded, priority="critical", due_date=str(date.today() + timedelta(days=30)))
    clock.freeze(clock.utcnow() + timedelta(days=7))  # the first task's deadline has passed
    h = as_user("abc")
    items = client.get(f"{API}/tasks", headers=h).json()["items"]
    assert items[0]["id"] == t["id"] and items[0]["is_overdue"] is True  # overdue beats critical
    assert items[1]["id"] == later["id"] and items[1]["is_overdue"] is False
    assert ids(client.get(f"{API}/tasks", params={"overdue": True}, headers=h)) == {t["id"]}


# ---------------------------------------------------------------- workflow


def test_assignee_acknowledges_and_it_is_tracked(client, as_user, seeded):
    t = make(client, as_user, seeded)
    d = client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()
    assert d["allowed_actions"] == ["start", "raise_blocker", "request_extension"]  # employee directly starts work
    r = client.post(f"{API}/tasks/{t['id']}/acknowledge", headers=as_user("abc"))
    assert r.status_code == 200 and r.json()["status"] == "acknowledged" and r.json()["acknowledged_at"]
    again = client.post(f"{API}/tasks/{t['id']}/acknowledge", headers=as_user("abc"))
    assert again.status_code == 409 and again.json()["code"] == "INVALID_TRANSITION"
    actions = [e["action"] for e in client.get(f"{API}/tasks/{t['id']}/timeline", headers=as_user("owner")).json()]
    assert "TASK_CREATED" in actions and "TASK_ACKNOWLEDGED" in actions


def test_only_the_assignee_can_acknowledge(client, as_user, seeded):
    t = make(client, as_user, seeded)
    assert client.post(f"{API}/tasks/{t['id']}/acknowledge", headers=as_user("owner")).status_code == 403
    assert client.post(f"{API}/tasks/{t['id']}/acknowledge", headers=as_user("devhead")).status_code == 403


def test_allowed_actions_depend_on_who_asks(client, as_user, seeded):
    t = make(client, as_user, seeded)
    mgmt = client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["allowed_actions"]
    assert set(mgmt) == {"edit", "reassign", "change_priority", "cancel", "change_deadline"}
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("hr1")).status_code == 404


def test_cancel_requires_reason_and_closes_the_task(client, as_user, seeded):
    t = make(client, as_user, seeded)
    h = as_user("owner")
    # Non-leadership roles cannot cancel
    assert client.post(f"{API}/tasks/{t['id']}/cancel", headers=as_user("manager"), json={"reason": "valid reason"}).status_code == 403
    assert client.post(f"{API}/tasks/{t['id']}/cancel", headers=as_user("abc"), json={"reason": "I do not want it"}).status_code == 403
    # Leadership requires reason min 3 chars
    assert client.post(f"{API}/tasks/{t['id']}/cancel", headers=h, json={"reason": "no"}).status_code == 422
    r = client.post(f"{API}/tasks/{t['id']}/cancel", headers=h, json={"reason": "Requirement dropped"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancel_reason"] == "Requirement dropped"
    assert client.post(f"{API}/tasks/{t['id']}/cancel", headers=h, json={"reason": "again please"}).status_code == 409
    assert client.post(f"{API}/tasks/{t['id']}/acknowledge", headers=as_user("abc")).status_code == 409
    assert client.patch(f"{API}/tasks/{t['id']}", headers=h, json={"title": "Edited after cancel"}).status_code == 409
    assert client.get(f"{API}/tasks/{t['id']}", headers=h).json()["allowed_actions"] == []


def test_reassign_moves_the_task_and_keeps_history(client, as_user, seeded):
    t = make(client, as_user, seeded, assignee=ABC)
    client.post(f"{API}/tasks/{t['id']}/acknowledge", headers=as_user("abc"))
    r = client.post(f"{API}/tasks/{t['id']}/reassign", headers=as_user("devhead"), json={"assignee_id": eid(seeded, FE), "reason": "ABC is on leave"})
    assert r.status_code == 200 and r.json()["assignee"]["full_name"] == "Frontend Dev"
    assert r.json()["status"] == "assigned" and r.json()["acknowledged_at"] is None  # fresh acknowledgement needed
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).status_code == 404  # ABC is out of the loop now
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("frontend")).status_code == 200
    with seeded() as s:
        rows = s.scalars(select(TaskAssignment).where(TaskAssignment.task_id == t["id"]).order_by(TaskAssignment.id)).all()
        assert len(rows) == 2 and rows[0].unassigned_at is not None and rows[1].unassigned_at is None


def test_reassign_obeys_scope_and_rank(client, as_user, seeded):
    t = make(client, as_user, seeded, assignee=ABC)
    h = as_user("devhead")
    assert client.post(f"{API}/tasks/{t['id']}/reassign", headers=h, json={"assignee_id": eid(seeded, HR1)}).status_code == 404
    assert client.post(f"{API}/tasks/{t['id']}/reassign", headers=h, json={"assignee_id": eid(seeded, ABC)}).status_code == 409
    assert client.post(f"{API}/tasks/{t['id']}/reassign", headers=as_user("abc"), json={"assignee_id": eid(seeded, FE)}).status_code == 403


def test_priority_change_is_audited(client, as_user, seeded):
    t = make(client, as_user, seeded, priority="low")
    assert client.post(f"{API}/tasks/{t['id']}/priority", headers=as_user("abc"), json={"priority": "critical"}).status_code == 403
    r = client.post(f"{API}/tasks/{t['id']}/priority", headers=as_user("manager"), json={"priority": "critical", "reason": "Client escalation"})
    assert r.status_code == 200 and r.json()["priority"] == "critical"
    assert client.post(f"{API}/tasks/{t['id']}/priority", headers=as_user("manager"), json={"priority": "urgent"}).status_code == 422
    tl = client.get(f"{API}/tasks/{t['id']}/timeline", headers=as_user("owner")).json()
    change = next(e for e in tl if e["action"] == "TASK_PRIORITY_CHANGED")
    assert change["before"] == {"priority": "low"} and change["after"]["priority"] == "critical" and change["actor"] == "Demo Manager"


def test_edit_fields_but_never_the_deadline(client, as_user, seeded):
    t = make(client, as_user, seeded)
    # Devhead cannot edit task (leadership only)
    assert client.patch(f"{API}/tasks/{t['id']}", headers=as_user("devhead"), json={"title": "Chatbot API v2"}).status_code == 403
    assert client.patch(f"{API}/tasks/{t['id']}", headers=as_user("abc"), json={"title": "Mine now"}).status_code == 403
    # Owner can edit task
    r = client.patch(f"{API}/tasks/{t['id']}", headers=as_user("owner"), json={"title": "Chatbot API v2", "estimated_hours": 16})
    assert r.status_code == 200 and r.json()["title"] == "Chatbot API v2" and r.json()["estimated_hours"] == 16
    assert client.patch(f"{API}/tasks/{t['id']}", headers=as_user("owner"), json={"due_at": "2030-01-01T00:00:00Z"}).status_code == 422
    assert client.patch(f"{API}/tasks/{t['id']}", headers=as_user("owner"), json={"assignee_id": 1}).status_code == 422
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["original_due_at"] == t["original_due_at"]


def test_state_machine_rejects_invalid_edges():
    from app.modules.tasks.state_machine import can_transition

    assert can_transition("assigned", "acknowledged", "assignee")
    assert not can_transition("assigned", "acknowledged", "manager")  # only the assignee acknowledges
    assert not can_transition("assigned", "completed", "assignee")  # must work on it first
    assert not can_transition("cancelled", "in_progress", "assignee")
    assert not can_transition("completed", "cancelled", "manager")  # closed tasks stay closed
    assert can_transition("completed", "reopened", "manager")  # revert
    assert not can_transition("completed", "reopened", "assignee")  # employees cannot revert their own work


# ---------------------------------------------------------------- workload: how much one person carries


def person(client, as_user, who, code):
    rows = client.get(f"{API}/workload", headers=as_user(who)).json()
    return next(r for r in rows if r["employee_id"] == code)


def test_owner_and_ceo_get_the_employee_list_with_load(client, as_user, seeded):
    make(client, as_user, seeded, priority="critical", estimated_hours=10)
    make(client, as_user, seeded, priority="high", estimated_hours=8)
    make(client, as_user, seeded, priority="low", estimated_hours=3)
    for who in ("owner", "ceo"):
        rows = client.get(f"{API}/workload", headers=as_user(who)).json()
        names = {r["full_name"] for r in rows}
        assert "ABC" in names and "Support Agent" in names and "Demo Admin" not in names
        abc = next(r for r in rows if r["full_name"] == "ABC")
        assert abc["open_tasks"] == 3 and abc["by_priority"] == {"critical": 1, "high": 1, "medium": 0, "low": 1}
        assert abc["open_estimated_hours"] == 21.0 and abc["by_status"]["assigned"] == 3
        assert rows[0]["full_name"] == "ABC"  # busiest person first


def test_workload_is_scoped_for_manager_and_heads(client, as_user, seeded):
    m = {r["full_name"] for r in client.get(f"{API}/workload", headers=as_user("manager")).json()}
    assert "Demo Owner" not in m and "Demo CEO" not in m and "ABC" in m and "Developers Head" in m
    d = {r["full_name"] for r in client.get(f"{API}/workload", headers=as_user("devhead")).json()}
    assert d == {"Developers Head", "ABC", "Frontend Dev", "HR Head", "Marketing Head"}  # own department + the other heads (peer assignment)
    assert client.get(f"{API}/workload", headers=as_user("abc")).status_code == 403
    assert client.get(f"{API}/workload", headers=as_user("admin")).status_code == 403


def test_workload_counts_overdue_and_flags_overload(client, as_user, seeded):
    make(client, as_user, seeded, estimated_hours=200, due_date=str(date.today() + timedelta(days=2)))
    abc = person(client, as_user, "owner", eid(seeded, ABC))
    assert abc["level"] == "overloaded" and abc["load_pct"] > 100 and abc["overdue_tasks"] == 0
    quiet = person(client, as_user, "owner", eid(seeded, FE))
    assert quiet["open_tasks"] == 0 and quiet["level"] == "normal"
    clock.freeze(clock.utcnow() + timedelta(days=4))
    assert person(client, as_user, "owner", eid(seeded, ABC))["overdue_tasks"] == 1


def test_workload_drops_closed_tasks(client, as_user, seeded):
    t = make(client, as_user, seeded)
    client.post(f"{API}/tasks/{t['id']}/cancel", headers=as_user("owner"), json={"reason": "Not needed anymore"})
    assert person(client, as_user, "owner", eid(seeded, ABC))["open_tasks"] == 0


def test_drill_down_to_one_persons_tasks(client, as_user, seeded):
    a = make(client, as_user, seeded, assignee=ABC)
    make(client, as_user, seeded, assignee=FE)
    got = client.get(f"{API}/tasks", params={"assignee_id": eid(seeded, ABC)}, headers=as_user("ceo")).json()
    assert [x["id"] for x in got["items"]] == [a["id"]]


# ---------------------------------------------------------------- projects + form metadata


def test_projects_and_meta(client, as_user, seeded):
    assert client.post(f"{API}/projects", headers=as_user("abc"), json={"code": "CHAT", "name": "Chatbot"}).status_code == 403
    r = client.post(f"{API}/projects", headers=as_user("owner"), json={"code": "chat", "name": "Chatbot Platform", "ends_on": str(date.today() + timedelta(days=30))})
    assert r.status_code == 201 and r.json()["code"] == "CHAT"
    assert client.post(f"{API}/projects", headers=as_user("manager"), json={"code": "CHAT", "name": "Dup", "ends_on": str(date.today() + timedelta(days=30))}).status_code == 409
    meta = client.get(f"{API}/task-meta", headers=as_user("owner")).json()
    assert "critical" in meta["priorities"] and any(p["code"] == "CHAT" for p in meta["projects"])
    assert any(c["name"] == "Development" for c in meta["categories"]) and any(t["name"] == "Bug" for t in meta["types"])
    t = make(client, as_user, seeded, project_id=r.json()["id"])
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["project"] == "Chatbot Platform"
    assert ids(client.get(f"{API}/tasks", params={"project_id": r.json()["id"]}, headers=as_user("owner"))) == {t["id"]}


def test_review_type_sets_requires_review(client, as_user, seeded):
    meta = client.get(f"{API}/task-meta", headers=as_user("owner")).json()
    review = next(t for t in meta["types"] if t["requires_review"])
    plain = next(t for t in meta["types"] if not t["requires_review"])
    assert make(client, as_user, seeded, type_id=review["id"])["requires_review"] is True
    assert make(client, as_user, seeded, type_id=plain["id"])["requires_review"] is False


# ---------------------------------------------------------------- attachments


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    return tmp_path


def up(client, headers, tid, name, data, ctype="application/octet-stream"):
    return client.post(f"{API}/tasks/{tid}/attachments", headers=headers, files={"file": (name, data, ctype)})


def test_attachment_upload_and_authorized_download(client, as_user, seeded, uploads):
    t = make(client, as_user, seeded)
    r = up(client, as_user("owner"), t["id"], "spec.pdf", b"%PDF-1.4 chatbot spec")
    assert r.status_code == 201 and r.json()["name"] == "spec.pdf" and r.json()["size_bytes"] == 21
    aid = r.json()["id"]
    dl = client.get(f"{API}/attachments/{aid}/download", headers=as_user("abc"))  # the assignee is in the loop
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 chatbot spec"
    assert dl.headers["content-disposition"].startswith("attachment")
    assert client.get(f"{API}/attachments/{aid}/download", headers=as_user("hrhead")).status_code == 404  # no leak
    assert client.get(f"{API}/attachments/{aid}/download").status_code == 401
    detail = client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()
    assert [a["name"] for a in detail["attachments"]] == ["spec.pdf"]
    assert not any(p.name == "spec.pdf" for p in uploads.rglob("*"))  # stored under a random name, not the original


def test_attachment_rejects_bad_files(client, as_user, seeded, uploads, monkeypatch):
    t = make(client, as_user, seeded)
    h = as_user("owner")
    assert up(client, h, t["id"], "run.exe", b"MZ\x90").status_code == 415  # type not allowed
    assert up(client, h, t["id"], "fake.pdf", b"<html>not a pdf</html>").json()["code"] == "FILE_CONTENT_MISMATCH"
    assert up(client, h, t["id"], "fake.png", b"%PDF-1.4").status_code == 415  # wrong signature for the extension
    assert up(client, h, t["id"], "empty.txt", b"").status_code == 422
    assert up(client, h, t["id"], "bin.txt", b"abc\x00def").status_code == 415  # binary pretending to be text
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    assert up(client, h, t["id"], "big.txt", b"a" * (1024 * 1024 + 1)).status_code == 413
    assert up(client, h, t["id"], "ok.csv", b"a,b\n1,2\n").status_code == 201


def test_attachment_filename_cannot_escape_the_upload_folder(client, as_user, seeded, uploads):
    t = make(client, as_user, seeded)
    r = up(client, as_user("owner"), t["id"], "../../evil.txt", b"hello")
    assert r.status_code == 201 and r.json()["name"] == "evil.txt"
    assert all(str(p).startswith(str(uploads)) for p in uploads.rglob("*"))


def test_cannot_upload_to_a_task_you_cannot_see(client, as_user, seeded, uploads):
    t = make(client, as_user, seeded)
    assert up(client, as_user("hrhead"), t["id"], "a.txt", b"hello").status_code == 404
    assert (
        db_count := len([p for p in uploads.rglob("*") if p.is_file()])
    ) == 0, db_count  # nothing was written to disk
    assert isinstance(db_count, int) and Task is not None


# ---------------------------------------------------------------- data integrity: commit BEFORE the response


def test_changes_are_committed_before_the_response_is_sent(seeded):
    """Regression: with FastAPI's default dependency scope the commit ran AFTER the response was sent, so a client
    could read stale data (and a failed commit would follow a 200). A probe with its own DB connection looks at
    the database the moment the endpoint has answered."""
    import re

    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import create_app

    from .conftest import login

    application = create_app()

    def _get_db():
        s = seeded()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    application.dependency_overrides[get_db] = _get_db
    seen: dict = {}

    @application.middleware("http")
    async def probe(request, call_next):
        response = await call_next(request)
        m = re.search(r"/tasks/(\d+)/acknowledge$", request.url.path)
        if m:
            with seeded() as other_connection:
                seen["status"] = other_connection.scalar(select(Task.status).where(Task.id == int(m.group(1))))
        return response

    with TestClient(application) as c:
        owner, abc = login(c, "owner@demo.example.com"), login(c, "abc@demo.example.com")
        t = c.post(f"{API}/tasks", headers=owner, json=body(seeded)).json()["task"]
        assert c.post(f"{API}/tasks/{t['id']}/acknowledge", headers=abc).status_code == 200
    assert seen["status"] == "acknowledged", "the change was not yet committed when the response went out"
