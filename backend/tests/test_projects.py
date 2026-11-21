"""Projects with expected results, points added later, a project head, and the review chain (ADR 003)."""

from datetime import date, timedelta

import pytest

from .helpers import ABC, API, DEVHEAD, FE, HR1, HRHEAD, eid, ok
from .test_notifications import relay

DUE = str(date.today() + timedelta(days=8))
FINISH = {"summary": "Implemented and checked the work.", "tested": True, "no_time_reason": "Quick change, done in minutes"}


def make_project(client, as_user, seeded, who="owner", **over):
    body = {
        "name": "Elala", "description": "The Elala platform", "expected_result": "A live Elala site with login and payments",
        "points": [{"title": "Design the login page", "expected_result": "Approved mock-up"}, {"title": "Build the API"}],
        "ends_on": str(date.today() + timedelta(days=30)),  # a project deadline is mandatory
    } | over
    r = client.post(f"{API}/projects", headers=as_user(who), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def detail(client, as_user, pid, who="owner"):
    r = client.get(f"{API}/projects/{pid}", headers=as_user(who))
    assert r.status_code == 200, r.text
    return r.json()


def assign_point(client, as_user, seeded, pid, point_id, assignee=ABC, who="owner", **over):
    body = {"assignee_id": eid(seeded, assignee), "priority": "high", "due_date": DUE, "estimated_hours": 4} | over
    return client.post(f"{API}/projects/{pid}/points/{point_id}/assign", headers=as_user(who), json=body)


def finish_task(client, as_user, who, tid):
    ok(client, as_user, who, tid, "start")
    return ok(client, as_user, who, tid, "complete", FINISH)


def review(client, as_user, who, tid, decision="approve", **over):
    return client.post(f"{API}/tasks/{tid}/review", headers=as_user(who), json={"decision": decision} | over)


def pending(client, as_user, who):
    r = client.get(f"{API}/tasks", headers=as_user(who), params={"awaiting_my_review": "true"})
    assert r.status_code == 200, r.text
    return {t["id"] for t in r.json()["items"]}


def notified(client, as_user, who, event):
    return [n for n in client.get(f"{API}/notifications", headers=as_user(who)).json()["items"] if n["event_type"] == event]


# ---------------------------------------------------------------- creating a project
def test_project_is_created_with_expected_result_head_team_and_points(client, as_user, seeded):
    pr = make_project(client, as_user, seeded, head_employee_id=eid(seeded, HRHEAD), member_ids=[eid(seeded, ABC), eid(seeded, FE)])
    d = detail(client, as_user, pr["id"])
    assert d["expected_result"].startswith("A live Elala") and d["status"] == "active"
    assert d["head"]["id"] == eid(seeded, HRHEAD) and {m["id"] for m in d["members"]} == {eid(seeded, ABC), eid(seeded, FE)}
    assert [(x["title"], x["status"]) for x in d["points"]] == [("Design the login page", "open"), ("Build the API", "open")]
    assert d["code"]  # generated when not supplied
    assert make_project(client, as_user, seeded)["code"] != d["code"]  # and unique


def test_head_and_team_must_be_active_employees(client, as_user, seeded):
    r = client.post(f"{API}/projects", headers=as_user("owner"), json={"name": "Bad", "head_employee_id": 999999})
    assert r.status_code == 422
    r = client.post(f"{API}/projects", headers=as_user("owner"), json={"name": "Bad", "member_ids": [999999]})
    assert r.status_code == 422


def test_employees_cannot_create_projects(client, as_user):
    assert client.post(f"{API}/projects", headers=as_user("abc"), json={"name": "Nope"}).status_code == 403


def test_named_head_and_team_are_told(client, as_user, seeded):
    make_project(client, as_user, seeded, head_employee_id=eid(seeded, HRHEAD), member_ids=[eid(seeded, ABC)])
    relay(seeded)
    assert notified(client, as_user, "hrhead", "PROJECT_HEAD_NAMED")
    assert notified(client, as_user, "abc", "PROJECT_MEMBER_ADDED")


def test_projects_are_visible_only_to_people_involved(client, as_user, seeded):
    pr = make_project(client, as_user, seeded, member_ids=[eid(seeded, ABC)])
    ids = lambda who: {p["id"] for p in client.get(f"{API}/projects", headers=as_user(who)).json()}  # noqa: E731
    assert pr["id"] in ids("owner") and pr["id"] in ids("ceo") and pr["id"] in ids("abc")
    assert pr["id"] not in ids("hr1")
    assert client.get(f"{API}/projects/{pr['id']}", headers=as_user("hr1")).status_code == 404


# ---------------------------------------------------------------- points added later, then assigned
def test_points_can_be_added_later_by_owner_and_ceo_but_not_employees(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, member_ids=[eid(seeded, ABC)])["id"]
    for who in ("owner", "ceo"):
        r = client.post(f"{API}/projects/{pid}/points", headers=as_user(who), json={"title": f"Remembered by {who}", "details": "more"})
        assert r.status_code == 201, r.text
    assert client.post(f"{API}/projects/{pid}/points", headers=as_user("abc"), json={"title": "I want this"}).status_code == 403
    assert len(detail(client, as_user, pid)["points"]) == 4


def test_a_point_can_be_edited_and_removed_until_it_is_assigned(client, as_user, seeded):
    pid = make_project(client, as_user, seeded)["id"]
    pts = detail(client, as_user, pid)["points"]
    r = client.patch(f"{API}/projects/{pid}/points/{pts[0]['id']}", headers=as_user("owner"), json={"title": "Design login and signup"})
    assert r.status_code == 200 and r.json()["title"] == "Design login and signup"
    assert client.delete(f"{API}/projects/{pid}/points/{pts[1]['id']}", headers=as_user("owner")).status_code == 204
    assert assign_point(client, as_user, seeded, pid, pts[0]["id"]).status_code == 201
    assert client.delete(f"{API}/projects/{pid}/points/{pts[0]['id']}", headers=as_user("owner")).status_code == 409
    assert client.patch(f"{API}/projects/{pid}/points/{pts[0]['id']}", headers=as_user("owner"), json={"title": "Changed"}).status_code == 409


def test_assigning_a_point_creates_a_linked_task_in_the_project(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, member_ids=[eid(seeded, ABC)])["id"]
    point = detail(client, as_user, pid)["points"][0]
    r = assign_point(client, as_user, seeded, pid, point["id"])
    assert r.status_code == 201, r.text
    task = r.json()["task"]
    assert task["project_id"] == pid and task["title"] == "Design the login page" and task["assignee"]["id"] == eid(seeded, ABC)
    d = detail(client, as_user, pid)
    assert d["points"][0]["status"] == "assigned" and d["points"][0]["task"]["id"] == task["id"]
    assert [t["id"] for t in d["tasks"]] == [task["id"]]
    assert assign_point(client, as_user, seeded, pid, point["id"]).status_code == 409  # only once


def test_with_a_team_only_team_members_can_be_assigned(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, member_ids=[eid(seeded, ABC)])["id"]
    point = detail(client, as_user, pid)["points"][0]
    r = assign_point(client, as_user, seeded, pid, point["id"], assignee=FE)
    assert r.status_code == 422 and r.json()["code"] == "NOT_ON_PROJECT_TEAM"
    direct = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Direct to FE", "description": "Direct task", "assignee_id": eid(seeded, FE), "priority": "low",
        "due_date": DUE, "estimated_hours": 1, "project_id": pid})
    assert direct.status_code == 422


def test_with_no_team_the_owner_assigns_directly_to_anyone(client, as_user, seeded):
    pid = make_project(client, as_user, seeded)["id"]
    point = detail(client, as_user, pid)["points"][0]
    assert assign_point(client, as_user, seeded, pid, point["id"], assignee=HR1).status_code == 201
    direct = client.post(f"{API}/tasks", headers=as_user("ceo"), json={
        "title": "Direct to FE", "description": "Direct task", "assignee_id": eid(seeded, FE), "priority": "low",
        "due_date": DUE, "estimated_hours": 1, "project_id": pid})
    assert direct.status_code == 201
    assert len(detail(client, as_user, pid)["tasks"]) == 2


def test_the_project_head_is_in_the_loop_when_work_is_assigned(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, head_employee_id=eid(seeded, HRHEAD))["id"]
    point = detail(client, as_user, pid)["points"][0]
    task = assign_point(client, as_user, seeded, pid, point["id"]).json()["task"]
    relay(seeded)
    hits = notified(client, as_user, "hrhead", "PROJECT_TASK_ASSIGNED")
    assert len(hits) == 1 and hits[0]["task_id"] == task["id"]
    assert client.get(f"{API}/tasks/{task['id']}", headers=as_user("hrhead")).status_code == 200  # head can see it
    assert client.get(f"{API}/tasks/{task['id']}", headers=as_user("hr1")).status_code == 404  # others still cannot


# ---------------------------------------------------------------- the review chain
def project_task(client, as_user, seeded, head=HRHEAD, assignee=ABC):
    pid = make_project(client, as_user, seeded, head_employee_id=eid(seeded, head) if head else None)["id"]
    point = detail(client, as_user, pid)["points"][0]
    return pid, assign_point(client, as_user, seeded, pid, point["id"], assignee=assignee).json()["task"]


def test_done_goes_to_the_head_then_to_leadership_then_completed(client, as_user, seeded):
    pid, t = project_task(client, as_user, seeded)
    done = finish_task(client, as_user, "abc", t["id"])
    assert done["status"] == "under_review" and done["review_stage"] == "head"
    assert t["id"] in pending(client, as_user, "hrhead")
    assert t["id"] not in pending(client, as_user, "owner") and t["id"] not in pending(client, as_user, "ceo")
    # leadership cannot skip the head; nobody else can approve for the head
    assert review(client, as_user, "owner", t["id"]).status_code == 403
    assert review(client, as_user, "devhead", t["id"]).status_code in (403, 404)
    assert review(client, as_user, "abc", t["id"]).status_code == 403
    r = review(client, as_user, "hrhead", t["id"], comment="Looks good")
    assert r.status_code == 200 and r.json()["status"] == "under_review" and r.json()["review_stage"] == "leadership"
    assert t["id"] not in pending(client, as_user, "hrhead")
    assert t["id"] in pending(client, as_user, "owner") and t["id"] in pending(client, as_user, "ceo")
    assert review(client, as_user, "hrhead", t["id"]).status_code == 403  # the head has done their part
    r = review(client, as_user, "ceo", t["id"], comment="Reviewed")
    assert r.status_code == 200 and r.json()["status"] == "completed" and r.json()["review_stage"] is None
    assert t["id"] not in pending(client, as_user, "owner")  # one of the two is enough


def test_without_a_head_done_goes_straight_to_leadership(client, as_user, seeded):
    pid, t = project_task(client, as_user, seeded, head=None, assignee="EMP-0011")  # Support has no department head
    done = finish_task(client, as_user, "support1", t["id"])
    assert done["status"] == "under_review" and done["review_stage"] == "leadership"
    assert t["id"] in pending(client, as_user, "owner") and t["id"] in pending(client, as_user, "ceo")
    assert review(client, as_user, "owner", t["id"]).json()["status"] == "completed"


def test_when_the_head_does_the_work_it_goes_to_leadership(client, as_user, seeded):
    pid, t = project_task(client, as_user, seeded, head=DEVHEAD, assignee=ABC)
    # reassign to the head themselves: the head cannot approve their own work
    ok(client, as_user, "owner", t["id"], "reassign", {"assignee_id": eid(seeded, DEVHEAD)})
    done = finish_task(client, as_user, "devhead", t["id"])
    assert done["review_stage"] == "leadership"


def test_the_head_or_leadership_can_send_work_back(client, as_user, seeded):
    pid, t = project_task(client, as_user, seeded)
    finish_task(client, as_user, "abc", t["id"])
    r = review(client, as_user, "hrhead", t["id"], "reject", reason_code="incomplete", comment="The login page is missing the error states")
    assert r.status_code == 200 and r.json()["status"] == "reopened" and r.json()["review_stage"] is None
    ok(client, as_user, "abc", t["id"], "start")
    ok(client, as_user, "abc", t["id"], "complete", FINISH)
    review(client, as_user, "hrhead", t["id"])
    r = review(client, as_user, "owner", t["id"], "reject", reason_code="qa_defect", comment="Fails on mobile")
    assert r.json()["status"] == "reopened" and r.json()["review_stage"] is None


def test_review_is_offered_only_to_the_person_whose_turn_it_is(client, as_user, seeded):
    pid, t = project_task(client, as_user, seeded)
    finish_task(client, as_user, "abc", t["id"])
    acts = lambda who: client.get(f"{API}/tasks/{t['id']}", headers=as_user(who)).json()["allowed_actions"]  # noqa: E731
    assert "review" in acts("hrhead") and "review" not in acts("owner")
    review(client, as_user, "hrhead", t["id"])
    assert "review" in acts("owner") and "review" in acts("ceo") and "review" not in acts("hrhead")


def test_head_stage_moves_to_leadership_if_the_head_is_removed(client, as_user, seeded):
    pid, t = project_task(client, as_user, seeded, assignee="EMP-0011")
    finish_task(client, as_user, "support1", t["id"])
    r = client.patch(f"{API}/projects/{pid}", headers=as_user("owner"), json={"head_employee_id": None})
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["review_stage"] == "leadership"
    assert t["id"] in pending(client, as_user, "owner")


def test_leadership_and_head_are_notified_at_each_step(client, as_user, seeded):
    pid, t = project_task(client, as_user, seeded)
    finish_task(client, as_user, "abc", t["id"])
    relay(seeded)
    assert notified(client, as_user, "hrhead", "TASK_HEAD_REVIEW_NEEDED")
    review(client, as_user, "hrhead", t["id"])
    relay(seeded)
    assert notified(client, as_user, "owner", "TASK_LEADERSHIP_REVIEW_NEEDED") and notified(client, as_user, "ceo", "TASK_LEADERSHIP_REVIEW_NEEDED")
    assert notified(client, as_user, "abc", "TASK_HEAD_APPROVED")


def test_tasks_outside_projects_keep_the_existing_flow(client, as_user, seeded):
    from .helpers import make

    t = make(client, as_user, seeded)
    done = finish_task(client, as_user, "abc", t["id"])
    assert done["status"] == "under_review" and done["review_stage"] == "head"  # ADR 008: the department head reviews first


# ---------------------------------------------------------------- completing the project
def test_project_completes_only_when_all_work_is_done_and_leadership_reviews(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, points=[{"title": "Only point"}])["id"]
    assert detail(client, as_user, pid)["ready_for_review"] is False  # nothing done yet
    assert client.post(f"{API}/projects/{pid}/complete", headers=as_user("owner"), json={}).status_code == 409
    point = detail(client, as_user, pid)["points"][0]
    t = assign_point(client, as_user, seeded, pid, point["id"], assignee="EMP-0011").json()["task"]
    finish_task(client, as_user, "support1", t["id"])
    assert detail(client, as_user, pid)["ready_for_review"] is False  # task not yet reviewed
    review(client, as_user, "ceo", t["id"])
    d = detail(client, as_user, pid)
    assert d["ready_for_review"] is True and d["status"] == "active" and d["points"][0]["status"] == "done"
    relay(seeded)
    assert notified(client, as_user, "owner", "PROJECT_READY_FOR_REVIEW") and notified(client, as_user, "ceo", "PROJECT_READY_FOR_REVIEW")
    for who in ("manager", "devhead", "abc"):
        assert client.post(f"{API}/projects/{pid}/complete", headers=as_user(who), json={}).status_code == 403
    r = client.post(f"{API}/projects/{pid}/complete", headers=as_user("owner"), json={"note": "All delivered"})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert detail(client, as_user, pid)["reviewed_by"]


def test_an_unassigned_point_blocks_project_completion(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, points=[{"title": "Point A"}, {"title": "Point B"}])["id"]
    pts = detail(client, as_user, pid)["points"]
    t = assign_point(client, as_user, seeded, pid, pts[0]["id"], assignee="EMP-0011").json()["task"]
    finish_task(client, as_user, "support1", t["id"])
    review(client, as_user, "owner", t["id"])
    assert detail(client, as_user, pid)["ready_for_review"] is False  # point B is still open
    assert client.post(f"{API}/projects/{pid}/complete", headers=as_user("owner"), json={}).status_code == 409


def test_adding_a_point_reopens_a_completed_project(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, points=[{"title": "Only point"}])["id"]
    t = assign_point(client, as_user, seeded, pid, detail(client, as_user, pid)["points"][0]["id"], assignee="EMP-0011").json()["task"]
    finish_task(client, as_user, "support1", t["id"])
    review(client, as_user, "owner", t["id"])
    client.post(f"{API}/projects/{pid}/complete", headers=as_user("owner"), json={})
    assert detail(client, as_user, pid)["status"] == "completed"
    assert client.post(f"{API}/projects/{pid}/points", headers=as_user("ceo"), json={"title": "I remembered one more thing"}).status_code == 201
    d = detail(client, as_user, pid)
    assert d["status"] == "active" and d["ready_for_review"] is False


def test_cancelled_tasks_do_not_block_completion(client, as_user, seeded):
    pid = make_project(client, as_user, seeded, points=[{"title": "Point A"}, {"title": "Point B"}])["id"]
    pts = detail(client, as_user, pid)["points"]
    t1 = assign_point(client, as_user, seeded, pid, pts[0]["id"], assignee="EMP-0011").json()["task"]
    t2 = assign_point(client, as_user, seeded, pid, pts[1]["id"], assignee=FE).json()["task"]
    finish_task(client, as_user, "support1", t1["id"])
    review(client, as_user, "owner", t1["id"])
    ok(client, as_user, "owner", t2["id"], "cancel", {"reason": "No longer needed"})
    assert detail(client, as_user, pid)["ready_for_review"] is True


# ---------------------------------------------------------------- email links work after deployment
def test_emails_carry_absolute_links_and_proper_headers(client, as_user, seeded, monkeypatch):
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.modules.notifications import mailer
    from app.modules.notifications.models import EmailLog

    monkeypatch.setattr(get_settings(), "app_base_url", "https://tasks.example-company.com/")
    pid, t = project_task(client, as_user, seeded)
    relay(seeded)
    with seeded() as s:
        row = s.scalar(select(EmailLog).where(EmailLog.subject.like("%New task%")))
        assert "https://tasks.example-company.com/tasks/" in row.body_text and "https://tasks.example-company.com//" not in row.body_text
        msg = mailer.build_message(row)
    assert msg["Message-ID"] and msg["Date"]  # mail without these is often filed as spam


def test_admin_is_warned_while_email_links_still_point_at_localhost(client, as_user, monkeypatch):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "app_base_url", "http://localhost:5173")
    assert client.get(f"{API}/admin/jobs/status", headers=as_user("admin")).json()["email_links_are_local"] is True
    monkeypatch.setattr(s, "app_base_url", "https://tasks.example-company.com")
    assert client.get(f"{API}/admin/jobs/status", headers=as_user("admin")).json()["email_links_are_local"] is False


@pytest.mark.parametrize("who", ["admin"])
def test_admin_has_no_projects(client, as_user, who):
    assert client.post(f"{API}/projects", headers=as_user(who), json={"name": "Nope"}).status_code == 403


# ---------------------------------------------------------------- deadline only: no effort estimate is asked for
def test_a_task_needs_only_a_deadline_not_an_effort_estimate(client, as_user, seeded):
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "No hours given", "description": "Only a deadline", "assignee_id": eid(seeded, ABC), "priority": "low", "due_date": DUE})
    assert r.status_code == 201, r.text
    assert r.json()["task"]["estimated_hours"] > 0  # an internal default keeps the workload maths working


def test_assigning_a_point_needs_only_a_deadline(client, as_user, seeded):
    pid = make_project(client, as_user, seeded)["id"]
    point = detail(client, as_user, pid)["points"][0]
    r = client.post(f"{API}/projects/{pid}/points/{point['id']}/assign", headers=as_user("owner"),
                    json={"assignee_id": eid(seeded, ABC), "priority": "high", "due_date": DUE})
    assert r.status_code == 201, r.text
