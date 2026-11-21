"""ADR 006: development flow. assignee finishes -> QA tests (bugs go back to the assignee) -> head -> CEO/Owner -> completed.
Head and QA are optional; with neither (and no project) a task is one employee's own work. Every message goes to the whole loop."""

from datetime import date, timedelta

from sqlalchemy import select

from app.modules.auth.models import User
from app.modules.notifications.models import EmailLog

from .helpers import ABC, API, DEVHEAD, FE, FINISH, HR1, at, eid, make, ok
from .test_notifications import by_user, emails_to, relay
from .test_projects import make_project, review

DONE = FINISH | {"no_time_reason": "Quick change, done in minutes"}


def task(client, as_user, tid, who="owner"):
    r = client.get(f"{API}/tasks/{tid}", headers=as_user(who))
    assert r.status_code == 200, r.text
    return r.json()


def finish(client, as_user, tid, who="abc"):
    ok(client, as_user, who, tid, "start")
    return ok(client, as_user, who, tid, "complete", DONE)


def dev_task(client, as_user, seeded, **over):
    at(0)
    return make(client, as_user, seeded, head_employee_id=eid(seeded, DEVHEAD), qa_employee_id=eid(seeded, FE), **over)


def test_deadline_has_no_time_and_the_loop_is_chosen_when_creating(client, as_user, seeded):
    t = dev_task(client, as_user, seeded)
    assert t["head"]["id"] == eid(seeded, DEVHEAD) and t["qa"]["id"] == eid(seeded, FE)
    d = date.today() + timedelta(days=6)
    assert t["due_at"] == f"{d}T13:00:00Z"  # the date, at the end of the working day (18:30 IST)


def test_full_flow_qa_finds_a_bug_the_developer_fixes_then_head_then_owner(client, as_user, seeded):
    t = dev_task(client, as_user, seeded)
    tid = t["id"]
    d = finish(client, as_user, tid)
    assert d["status"] == "under_review" and d["review_stage"] == "qa"
    relay(seeded)
    assert set(by_user(seeded, "TASK_QA_REVIEW_NEEDED")) == {"frontend"}  # the QA is told, nobody else asked to review yet
    assert "frontend" in emails_to(seeded, "TASK_QA_REVIEW_NEEDED")
    assert not by_user(seeded, "TASK_HEAD_REVIEW_NEEDED")

    # only the QA may act at this step: not the head, not the Owner
    assert review(client, as_user, "devhead", tid).status_code == 403
    assert review(client, as_user, "owner", tid).status_code == 403
    assert "review" in task(client, as_user, tid, "frontend")["allowed_actions"]
    assert "review" not in task(client, as_user, tid, "owner")["allowed_actions"]

    # QA finds a bug: it must say what is wrong, and it goes back to the developer
    assert review(client, as_user, "frontend", tid, "reject").status_code == 422
    r = review(client, as_user, "frontend", tid, "reject", comment="The login button does nothing on mobile")
    assert r.status_code == 200 and r.json()["status"] == "reopened" and r.json()["review_stage"] is None
    assert r.json()["reverts"][-1]["found_by"] == "QA" and r.json()["reverts"][-1]["reason_code"] == "qa_defect"
    relay(seeded)
    assert "abc" in by_user(seeded, "TASK_REVIEW_REJECTED")  # the developer is told...
    rej = by_user(seeded, "TASK_REVIEW_REJECTED")
    assert {"abc", "devhead", "owner"} <= set(rej)  # ...and so is everybody in the loop
    assert "login button does nothing" in rej["devhead"][0].body

    # the developer resolves it and submits again: back to QA (a full re-test), not straight to the head
    d = finish(client, as_user, tid)
    assert d["status"] == "under_review" and d["review_stage"] == "qa"

    # QA ticks "bugs solved": it moves to the head
    r = review(client, as_user, "frontend", tid, comment="All bugs solved")
    assert r.status_code == 200 and r.json()["review_stage"] == "head" and r.json()["status"] == "under_review"
    relay(seeded)
    assert "devhead" in by_user(seeded, "TASK_HEAD_REVIEW_NEEDED")
    assert review(client, as_user, "frontend", tid).status_code == 403  # QA's turn is over
    assert "review" in task(client, as_user, tid, "devhead")["allowed_actions"]

    # the head approves: it moves to CEO/Owner
    r = review(client, as_user, "devhead", tid)
    assert r.json()["review_stage"] == "leadership"
    relay(seeded)
    assert {"owner", "ceo"} <= set(by_user(seeded, "TASK_LEADERSHIP_REVIEW_NEEDED"))
    assert review(client, as_user, "devhead", tid).status_code == 403

    # one of them completes it: the task is Completed and the whole loop hears about it
    r = review(client, as_user, "ceo", tid, comment="Looks good")
    assert r.json()["status"] == "completed" and r.json()["review_stage"] is None and r.json()["completed_at"]
    relay(seeded)
    done = by_user(seeded, "TASK_REVIEW_APPROVED")
    assert {"abc", "devhead", "frontend", "owner"} <= set(done) and "ceo" not in done


def test_without_a_qa_it_goes_to_the_head_and_without_a_head_straight_to_leadership(client, as_user, seeded):
    at(0)
    only_head = make(client, as_user, seeded, head_employee_id=eid(seeded, DEVHEAD))
    assert finish(client, as_user, only_head["id"])["review_stage"] == "head"
    only_qa = make(client, as_user, seeded, qa_employee_id=eid(seeded, FE), title="Another task")
    d = finish(client, as_user, only_qa["id"])
    assert d["review_stage"] == "qa"
    d = review(client, as_user, "frontend", only_qa["id"]).json()
    assert d["review_stage"] == "head"  # ADR 008: nobody named, so the head of ABC's department reviews next
    d = review(client, as_user, "devhead", only_qa["id"]).json()
    assert d["review_stage"] == "leadership"
    assert review(client, as_user, "owner", only_qa["id"]).json()["status"] == "completed"
    # a department without a head goes straight to the CEO/Owner
    sup = make(client, as_user, seeded, assignee="EMP-0011", title="Support task")
    assert finish(client, as_user, sup["id"], who="support1")["review_stage"] == "leadership"


def test_a_task_without_head_or_qa_goes_to_ceo_owner_review(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, assignee="EMP-0011")  # Support: no department head, no QA tester
    assert t["head"] is None and t["qa"] is None
    d = finish(client, as_user, t["id"], who="support1")
    assert d["status"] == "under_review" and d["review_stage"] == "leadership"  # ADR 008: CEO/Owner review it
    # only the Owner/CEO's own work completes directly
    own = make(client, as_user, seeded, assignee="EMP-0002", title="CEO task")
    assert finish(client, as_user, own["id"], who="ceo")["status"] == "completed"


def test_nobody_reviews_their_own_work_the_qa_or_head_who_is_the_assignee_is_skipped(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, qa_employee_id=eid(seeded, ABC), head_employee_id=eid(seeded, ABC))
    assert finish(client, as_user, t["id"])["review_stage"] == "leadership"


def test_the_qa_can_see_and_discuss_a_task_outside_their_department(client, as_user, seeded):
    t = dev_task(client, as_user, seeded)
    outsider = make(client, as_user, seeded, title="Not mine")
    assert as_user("hr1") is not None
    assert client.get(f"{API}/tasks/{outsider['id']}", headers=as_user("hr1")).status_code == 404
    # make HR1 the QA of a task: now it is visible to them and they may comment
    mine = make(client, as_user, seeded, title="HR QA task", qa_employee_id=eid(seeded, HR1))
    assert client.get(f"{API}/tasks/{mine['id']}", headers=as_user("hr1")).status_code == 200
    r = client.post(f"{API}/tasks/{mine['id']}/comments", headers=as_user("hr1"), json={"kind": "comment", "body": "I will test this"})
    assert r.status_code == 201
    assert t["id"]


def test_every_comment_goes_in_full_to_the_email_of_everyone_in_the_loop(client, as_user, seeded):
    t = dev_task(client, as_user, seeded)
    text = "Please check the OTP screen.\nIt fails when the number starts with 0."
    r = client.post(f"{API}/tasks/{t['id']}/comments", headers=as_user("abc"), json={"kind": "comment", "body": text})
    assert r.status_code == 201
    relay(seeded)
    got = by_user(seeded, "COMMENT_ADDED")
    assert {"owner", "devhead", "frontend"} <= set(got) and "abc" not in got  # head, QA and assigner; not the author
    assert {"owner", "devhead", "frontend"} <= set(emails_to(seeded, "COMMENT_ADDED"))
    with seeded() as s:
        row = s.scalars(select(EmailLog).join(User, User.id == EmailLog.to_user_id).where(User.email.like("frontend@%"), EmailLog.subject.like("%Comment%"))).first()
    assert text in row.body_text and "It fails when the number starts with 0." in row.body_text  # the whole message, not a snippet
    assert "QA: Frontend Dev" in row.body_text and "Head: Developers Head" in row.body_text and "Assigned to: ABC" in row.body_text
    assert "white-space:pre-wrap" in row.body_html  # line breaks survive in HTML mail


def test_a_long_comment_is_not_cut_short(client, as_user, seeded):
    t = dev_task(client, as_user, seeded)
    long = "x" * 1500
    client.post(f"{API}/tasks/{t['id']}/comments", headers=as_user("abc"), json={"kind": "question", "body": long})
    relay(seeded)
    with seeded() as s:
        row = s.scalars(select(EmailLog).where(EmailLog.subject.like("%Question%"))).first()
    assert long in row.body_text


def test_the_project_qa_and_head_apply_to_its_tasks_and_the_team_is_in_the_loop(client, as_user, seeded):
    pr = make_project(client, as_user, seeded, head_employee_id=eid(seeded, DEVHEAD), qa_employee_id=eid(seeded, FE),
                      member_ids=[eid(seeded, ABC), eid(seeded, HR1)])
    assert pr["qa"]["id"] == eid(seeded, FE)
    at(0)
    t = make(client, as_user, seeded, project_id=pr["id"])
    assert t["head"]["id"] == eid(seeded, DEVHEAD) and t["qa"]["id"] == eid(seeded, FE)  # inherited
    assert finish(client, as_user, t["id"])["review_stage"] == "qa"
    client.post(f"{API}/tasks/{t['id']}/comments", headers=as_user("abc"), json={"kind": "comment", "body": "Ready for testing"})
    relay(seeded)
    assert {"devhead", "frontend", "hr1", "owner"} <= set(by_user(seeded, "COMMENT_ADDED"))  # members of the project too


def test_removing_the_qa_moves_waiting_work_on(client, as_user, seeded):
    pr = make_project(client, as_user, seeded, head_employee_id=eid(seeded, DEVHEAD), qa_employee_id=eid(seeded, FE))
    at(0)
    t = make(client, as_user, seeded, project_id=pr["id"])
    assert finish(client, as_user, t["id"])["review_stage"] == "qa"
    r = client.patch(f"{API}/projects/{pr['id']}", headers=as_user("owner"), json={"qa_employee_id": None})
    assert r.status_code == 200
    assert task(client, as_user, t["id"])["review_stage"] == "head"


def test_head_and_qa_must_be_active_employees_and_the_loop_can_be_edited(client, as_user, seeded):
    at(0)
    h = as_user("owner")
    bad = client.post(f"{API}/tasks", headers=h, json={"title": "Bad one", "description": "desc", "assignee_id": eid(seeded, ABC), "priority": "low",
                                                      "due_date": str(date.today() + timedelta(days=5)), "qa_employee_id": 999999})
    assert bad.status_code == 422
    t = make(client, as_user, seeded)
    r = client.patch(f"{API}/tasks/{t['id']}", headers=h, json={"qa_employee_id": eid(seeded, FE), "head_employee_id": eid(seeded, DEVHEAD)})
    assert r.status_code == 200 and r.json()["qa"]["id"] == eid(seeded, FE) and r.json()["head"]["id"] == eid(seeded, DEVHEAD)
    relay(seeded)
    assert "frontend" in by_user(seeded, "TASK_QA_ASSIGNED")  # told they are the QA
