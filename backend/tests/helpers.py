"""Shared helpers for the task/time tests."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from app.core import clock
from app.modules.org.models import Employee

API = "/api/v1"
ABC, FE, DEVHEAD, HRHEAD, HR1, MANAGER, CEO, OWNER, ADMIN, SUPPORT = (
    "EMP-0007", "EMP-0008", "EMP-0004", "EMP-0005", "EMP-0009", "EMP-0003", "EMP-0002", "EMP-0001", "EMP-0000", "EMP-0011",
)  # fmt: skip

# 09:30 IST tomorrow, as naive UTC. Every timing test is expressed as "minutes after BASE".
BASE = datetime.combine(date.today() + timedelta(days=1), time(4, 0))


def eid(seeded, code):
    with seeded() as s:
        return s.scalar(select(Employee.id).where(Employee.employee_code == code))


def at(minutes: float) -> datetime:
    """Move the server clock to BASE + minutes (09:30 IST tomorrow + minutes)."""
    clock.freeze(BASE + timedelta(minutes=minutes))
    return clock.utcnow()


def body(seeded, assignee=ABC, **over):
    return {
        "title": "Develop AI Chatbot API", "description": "Develop and integrate the chatbot API.",
        "assignee_id": eid(seeded, assignee), "priority": "high",
        "due_date": str(date.today() + timedelta(days=6)), "estimated_hours": 12,
    } | over  # fmt: skip


def make(client, as_user, seeded, who="owner", assignee=ABC, **over):
    r = client.post(f"{API}/tasks", headers=as_user(who), json=body(seeded, assignee, **over))
    assert r.status_code == 201, r.text
    return r.json()["task"]


def do(client, as_user, who, tid, action, json=None):
    """POST /tasks/{id}/<action> as `who`; returns the response (never asserts)."""
    return client.post(f"{API}/tasks/{tid}/{action}", headers=as_user(who), json=json if json is not None else {})


def ok(client, as_user, who, tid, action, json=None):
    r = do(client, as_user, who, tid, action, json)
    assert r.status_code == 200, f"{who} {action}: {r.status_code} {r.text}"
    return r.json()


FINISH = {"summary": "Implemented and verified the chatbot API.", "tested": True}


REVIEWERS = ("frontend", "devhead", "hrhead", "mktghead", "manager", "owner", "ceo")


def approve_through(client, as_user, tid):
    """ADR 008: every task an employee finishes is reviewed (QA -> head -> CEO/Owner). Approve each stage as whoever's turn it is
    until the task is Completed. Returns the final task."""
    for _ in range(4):
        d = client.get(f"{API}/tasks/{tid}", headers=as_user("owner")).json()
        if d["status"] != "under_review":
            return d
        for who in REVIEWERS:
            if client.post(f"{API}/tasks/{tid}/review", headers=as_user(who), json={"decision": "approve"}).status_code == 200:
                break
        else:
            raise AssertionError(f"nobody could review stage {d['review_stage']}")
    return client.get(f"{API}/tasks/{tid}", headers=as_user("owner")).json()


def complete_fully(client, as_user, who, tid, payload=None):
    """The assignee finishes, then the whole review chain approves. Returns the Completed task."""
    ok(client, as_user, who, tid, "complete", payload if payload is not None else FINISH)
    return approve_through(client, as_user, tid)
