"""Heads in the loop: peer-head assignment (everyone told) and a Department Head taking ownership of a task."""

from .helpers import ABC, API, HRHEAD, eid, make
from .test_notifications import by_user, relay


def test_head_can_assign_to_another_head_and_everyone_is_in_the_loop(client, as_user, seeded):
    t = make(client, as_user, seeded, who="devhead", assignee=HRHEAD, title="Share the onboarding checklist")
    assert t["assignee"]["full_name"] == "HR Head" and t["assigned_by"]["full_name"] == "Developers Head"
    relay(seeded)
    got = by_user(seeded, "TASK_CREATED")
    assert {"hrhead", "manager", "ceo", "owner"} <= set(got)  # the other head, the Manager above both, CEO and Owner
    assert "devhead" not in got  # the assigner is not told about their own action
    for who in ("hrhead", "devhead", "manager", "ceo", "owner"):  # all of them can open it
        assert client.get(f"{API}/tasks/{t['id']}", headers=as_user(who)).status_code == 200, who
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("mktghead")).status_code == 404  # unrelated head


def test_head_still_cannot_assign_outside_department_to_regular_staff(client, as_user, seeded):
    r = client.post(f"{API}/tasks", headers=as_user("devhead"), json={
        "title": "Not yours", "description": "Another department's employee.", "assignee_id": eid(seeded, "EMP-0009"),
        "priority": "low", "due_date": "2099-01-01", "estimated_hours": 1})
    assert r.status_code == 404  # HR1 sits outside Developers
    r = client.post(f"{API}/tasks", headers=as_user("devhead"), json={
        "title": "Upward", "description": "Upward assignment.", "assignee_id": eid(seeded, "EMP-0003"),
        "priority": "low", "due_date": "2099-01-01", "estimated_hours": 1})
    assert r.status_code in (403, 404)  # never to the Manager


def test_employee_cannot_use_peer_assignment(client, as_user, seeded):
    r = client.post(f"{API}/tasks", headers=as_user("abc"), json={
        "title": "x", "description": "x", "assignee_id": eid(seeded, HRHEAD), "priority": "low", "due_date": "2099-01-01", "estimated_hours": 1})
    assert r.status_code == 403


def test_workload_picker_lists_other_heads_for_a_head(client, as_user, seeded):
    names = {r["full_name"] for r in client.get(f"{API}/workload", headers=as_user("hrhead")).json()}
    assert {"Developers Head", "Marketing Head"} <= names and "ABC" not in names


def test_department_head_takes_ownership_once(client, as_user, seeded):
    # Requirement 1: ownership was removed; department head is already accountable and in the loop
    t = make(client, as_user, seeded, who="owner", assignee=ABC)
    d = client.get(f"{API}/tasks/{t['id']}", headers=as_user("devhead")).json()
    assert "take_ownership" not in d["allowed_actions"] and d["head"]["full_name"] == "Developers Head"


def test_only_the_right_head_may_take_ownership(client, as_user, seeded):
    t = make(client, as_user, seeded, who="owner", assignee=ABC)
    for who in ("hrhead", "manager", "abc", "ceo", "devhead"):
        d = client.get(f"{API}/tasks/{t['id']}", headers=as_user(who))
        if d.status_code == 200:
            assert "take_ownership" not in d.json()["allowed_actions"], who
