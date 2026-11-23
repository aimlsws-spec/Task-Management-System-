"""ADR 008: who reviews finished work when nobody is named: the assignee's department QA tester and head, then CEO/Owner.
Plus the role flows from the brief: heads assign to each other and to employees, leadership sees blockers and overdue work."""

from datetime import date, timedelta

from sqlalchemy import select

from app.modules.org.models import Department

from .helpers import API, DEVHEAD, FE, FINISH, HRHEAD, SUPPORT, at, eid, make, ok
from .test_notifications import by_user, emails_to, relay

DONE = FINISH | {"no_time_reason": "Quick change"}


def dept(seeded, code):
    with seeded() as s:
        return s.scalar(select(Department.id).where(Department.code == code))


def finish(client, as_user, tid, who="abc"):
    ok(client, as_user, who, tid, "start")
    return ok(client, as_user, who, tid, "complete", DONE)


def review(client, as_user, who, tid, decision="approve", **over):
    return client.post(f"{API}/tasks/{tid}/review", headers=as_user(who), json={"decision": decision} | over)


def set_qa(client, as_user, seeded, code, qa_code, who="admin"):
    return client.put(f"{API}/departments/{dept(seeded, code)}/qa", headers=as_user(who), json={"qa_employee_id": eid(seeded, qa_code) if qa_code else None})


# ---------------------------------------------------------------- department QA tester


def test_only_the_admin_sets_a_department_qa_tester(client, as_user, seeded):
    for who in ("devhead", "abc"):
        assert set_qa(client, as_user, seeded, "DEV", FE, who).status_code in (403, 404)
    r = set_qa(client, as_user, seeded, "DEV", FE, "owner")
    assert r.status_code == 200 and r.json()["qa_employee_id"] == eid(seeded, FE)
    assert set_qa(client, as_user, seeded, "DEV", None, "admin").json()["qa_employee_id"] is None


def test_development_work_goes_to_the_department_qa_then_the_head_then_leadership(client, as_user, seeded):
    set_qa(client, as_user, seeded, "DEV", FE)
    at(0)
    t = make(client, as_user, seeded)  # no head or QA named anywhere
    assert t["qa"]["id"] == eid(seeded, FE) and t["head"]["id"] == eid(seeded, DEVHEAD)
    d = finish(client, as_user, t["id"])
    assert d["status"] == "under_review" and d["review_stage"] == "qa"
    relay(seeded)
    assert set(by_user(seeded, "TASK_QA_REVIEW_NEEDED")) == {"frontend"}
    assert review(client, as_user, "devhead", t["id"]).status_code == 403  # not the head's turn yet
    r = review(client, as_user, "frontend", t["id"])
    assert r.status_code == 200, r.text
    assert r.json()["review_stage"] == "head"
    assert review(client, as_user, "owner", t["id"]).status_code == 403  # leadership cannot skip the head
    assert review(client, as_user, "devhead", t["id"]).json()["review_stage"] == "leadership"
    done = review(client, as_user, "ceo", t["id"])  # one of CEO / Owner is enough
    assert done.status_code == 200 and done.json()["status"] == "completed"


def test_the_qa_tester_does_not_test_their_own_work(client, as_user, seeded):
    set_qa(client, as_user, seeded, "DEV", FE)
    at(0)
    t = make(client, as_user, seeded, assignee=FE)
    assert t["qa"] is None  # the tester is the assignee: that step is skipped
    d = finish(client, as_user, t["id"], who="frontend")
    assert d["review_stage"] == "head"


def test_a_task_or_project_qa_beats_the_department_qa(client, as_user, seeded):
    set_qa(client, as_user, seeded, "DEV", FE)
    at(0)
    t = make(client, as_user, seeded, qa_employee_id=eid(seeded, HRHEAD))
    assert t["qa"]["id"] == eid(seeded, HRHEAD)


# ---------------------------------------------------------------- the head reviews; no head means CEO/Owner


def test_the_department_head_reviews_before_leadership(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    d = finish(client, as_user, t["id"])
    assert d["review_stage"] == "head"
    relay(seeded)
    assert set(by_user(seeded, "TASK_HEAD_REVIEW_NEEDED")) == {"devhead"} and "devhead" in emails_to(seeded, "TASK_HEAD_REVIEW_NEEDED")
    assert review(client, as_user, "devhead", t["id"]).json()["review_stage"] == "leadership"
    relay(seeded)
    assert {"owner", "ceo"} <= set(by_user(seeded, "TASK_LEADERSHIP_REVIEW_NEEDED"))
    assert review(client, as_user, "owner", t["id"]).json()["status"] == "completed"


def test_a_department_without_a_head_sends_work_straight_to_ceo_and_owner(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, assignee=SUPPORT)
    d = finish(client, as_user, t["id"], who="support1")
    assert d["review_stage"] == "leadership"
    relay(seeded)
    assert {"owner", "ceo"} <= set(by_user(seeded, "TASK_LEADERSHIP_REVIEW_NEEDED"))
    assert review(client, as_user, "manager", t["id"]).status_code == 403
    assert review(client, as_user, "owner", t["id"]).json()["status"] == "completed"


def test_the_owner_and_ceo_complete_their_own_work_directly(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, assignee="EMP-0002")
    assert finish(client, as_user, t["id"], who="ceo")["status"] == "completed"


def test_bugs_found_by_the_head_send_it_back_to_the_employee(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    finish(client, as_user, t["id"])
    r = review(client, as_user, "devhead", t["id"], "reject", reason_code="incomplete", comment="Handle the empty case")
    assert r.status_code == 200 and r.json()["status"] == "reopened"
    assert ok(client, as_user, "abc", t["id"], "start")["status"] == "in_progress"  # the employee picks it up again


# ---------------------------------------------------------------- the head is in the loop


def test_the_department_head_hears_about_new_work_and_messages_for_their_team(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    relay(seeded)
    assert "devhead" in by_user(seeded, "TASK_CREATED") and "devhead" in emails_to(seeded, "TASK_CREATED")
    r = client.post(f"{API}/tasks/{t['id']}/comments", headers=as_user("abc"), json={"body": "Started on this today"})
    assert r.status_code in (200, 201), r.text
    relay(seeded)
    assert "devhead" in by_user(seeded, "COMMENT_ADDED") and "owner" in by_user(seeded, "COMMENT_ADDED")


# ---------------------------------------------------------------- heads work together


def test_heads_assign_tasks_to_each_other_and_to_employees_and_leadership_sees_them(client, as_user, seeded):
    at(0)
    to_head = make(client, as_user, seeded, who="devhead", assignee=HRHEAD, title="Review hiring plan")
    to_emp = make(client, as_user, seeded, who="devhead", assignee="EMP-0007", title="Chatbot fix")
    assert to_head["assignee"]["id"] == eid(seeded, HRHEAD) and to_emp["assignee"]["id"] == eid(seeded, "EMP-0007")
    for who in ("owner", "ceo"):
        titles = {x["title"] for x in client.get(f"{API}/tasks", headers=as_user(who)).json()["items"]}
        assert {"Review hiring plan", "Chatbot fix"} <= titles
    relay(seeded)
    assert "hrhead" in by_user(seeded, "TASK_CREATED") and "abc" in by_user(seeded, "TASK_CREATED")


# ---------------------------------------------------------------- leadership sees blockers and overdue work


def test_a_blocker_reaches_the_head_and_leadership_can_see_it(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, priority="critical")
    ok(client, as_user, "abc", t["id"], "start")
    from .test_blockers import raise_b  # noqa: PLC0415

    r = raise_b(client, as_user, t["id"])
    assert r.status_code in (200, 201), r.text
    relay(seeded)
    assert "devhead" in by_user(seeded, "BLOCKER_RAISED")
    for who in ("owner", "ceo"):
        assert client.get(f"{API}/blockers", headers=as_user(who)).status_code == 200


def test_an_overdue_task_tells_leadership_and_the_head_with_the_employee_name(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, due_date=str(date.today() + timedelta(days=1)))
    from app.core import clock  # noqa: PLC0415
    from app.jobs import scheduler  # noqa: PLC0415
    from tests.helpers import BASE  # noqa: PLC0415

    clock.freeze(BASE + timedelta(days=3))
    with seeded() as s:
        scheduler.tick(s, clock.utcnow())
        s.commit()
    relay(seeded)
    got = by_user(seeded, "TASK_OVERDUE")
    assert {"abc", "devhead", "owner", "ceo"} <= set(got)
    text = got["owner"][0].title + " " + (got["owner"][0].body or "")
    assert "ABC" in text and "Develop AI Chatbot API" in text
    assert t["id"]
