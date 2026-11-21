"""Phase 5: an overdue task cannot be ignored. The employee must explain; managers decide; nothing is ever erased."""

from datetime import date, datetime, timedelta

import pytest

from app.core import clock
from app.modules.tasks.delays import escalation_level, escalation_times

from .helpers import ABC, API, FINISH, approve_through, at, do, make, ok


def overdue_task(client, as_user, seeded, start=True, late_days=1, assignee=ABC, worker="abc", creator="owner", **over):
    """A task whose deadline has passed `late_days` ago. The clock is left frozen at that moment."""
    at(0)
    t = make(client, as_user, seeded, who=creator, assignee=assignee, **over)
    if start:
        ok(client, as_user, worker, t["id"], "start")
    due = datetime.fromisoformat(t["due_at"].rstrip("Z"))
    clock.freeze(due + timedelta(days=late_days))
    return t


def explain(client, as_user, tid, who="abc", **over):
    body = {
        "reason": "The vendor API credentials arrived three days late", "progress_pct": 60,
        "work_completed": "Authentication and the data layer are done", "remaining_work": "Endpoints and tests",
        "blockers": "Waiting for sandbox access", "expected_date": str(clock.utcnow().date() + timedelta(days=3)),
    } | over  # fmt: skip
    return client.post(f"{API}/tasks/{tid}/delay-reasons", headers=as_user(who), json=body)


def detail(client, as_user, tid, who="abc"):
    return client.get(f"{API}/tasks/{tid}", headers=as_user(who)).json()


def review(client, as_user, rid, decision, who="manager", **over):
    return client.post(f"{API}/delay-reasons/{rid}/review", headers=as_user(who), json={"decision": decision} | over)


# ---------------------------------------------------------------- the requirement


def test_not_overdue_means_nothing_is_required(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    d = detail(client, as_user, t["id"])
    assert d["delay"]["required"] is False and d["delay"]["overdue"] is False and "explain_delay" not in d["allowed_actions"]
    r = explain(client, as_user, t["id"])
    assert r.status_code == 409 and r.json()["code"] == "NOT_OVERDUE"  # the way to ask for time is an extension request


def test_overdue_task_demands_an_explanation(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    d = detail(client, as_user, t["id"])
    assert d["is_overdue"] is True and d["delay"]["required"] is True and d["delay"]["why"] == "none_submitted"
    assert "explain_delay" in d["allowed_actions"]
    items = client.get(f"{API}/tasks", headers=as_user("abc")).json()["items"]
    assert items[0]["explanation_required"] is True and items[0]["is_overdue"] is True  # the list flags it too
    assert client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["delay"]["required"] is True  # management sees it


def test_the_employee_submits_a_full_explanation(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    r = explain(client, as_user, t["id"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["delay"]["required"] is False and d["is_overdue"] is True  # explained, but still overdue until it is done
    item = d["delay"]["items"][0]
    assert item["kind"] == "initial" and item["progress_pct"] == 60 and item["blockers"] == "Waiting for sandbox access" and item["at"]
    assert d["progress_pct"] == 60 and d["delay"]["awaiting_review"] is True
    assert "Delay explanation" in d["updates"][0]["note"]  # also visible in the progress history


def test_explanation_validation(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    assert explain(client, as_user, t["id"], reason="x").status_code == 422
    assert explain(client, as_user, t["id"], progress_pct=101).status_code == 422
    assert explain(client, as_user, t["id"], remaining_work="").status_code == 422
    past = str(clock.utcnow().date() - timedelta(days=1))
    assert explain(client, as_user, t["id"], expected_date=past).json()["code"] == "EXPECTED_IN_PAST"
    assert explain(client, as_user, t["id"], attachment_id=999999).json()["code"] == "INVALID_ATTACHMENT"
    assert explain(client, as_user, t["id"], who="owner").status_code == 403  # only the assignee explains
    assert explain(client, as_user, t["id"], who="devhead").status_code == 403
    assert explain(client, as_user, t["id"]) .status_code == 201


def test_explanations_are_append_only(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    first = explain(client, as_user, t["id"]).json()["delay"]["items"][0]
    second = explain(client, as_user, t["id"], reason="Update: sandbox access arrived, finishing now", progress_pct=85).json()["delay"]["items"]
    assert [i["kind"] for i in second] == ["update", "initial"]  # newest first, the first one untouched
    assert second[1]["reason"] == first["reason"] and second[1]["id"] == first["id"]
    for method in ("put", "patch", "delete"):  # there is no way to edit or remove one
        r = getattr(client, method)(f"{API}/delay-reasons/{first['id']}", headers=as_user("abc"))
        assert r.status_code in (404, 405)


def test_who_can_read_explanations(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    for who in ("abc", "devhead", "manager"):
        assert len(client.get(f"{API}/tasks/{t['id']}/delay-reasons", headers=as_user(who)).json()) == 1, who
    for who in ("owner", "ceo"):  # leadership sees nothing until the line approves it
        assert client.get(f"{API}/tasks/{t['id']}/delay-reasons", headers=as_user(who)).json() == [], who
    assert client.get(f"{API}/tasks/{t['id']}/delay-reasons", headers=as_user("hrhead")).status_code == 404


# ---------------------------------------------------------------- it cannot be dismissed: finishing needs it


def test_cannot_finish_an_overdue_task_without_explaining(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    r = do(client, as_user, "abc", t["id"], "complete", FINISH)
    assert r.status_code == 409 and r.json()["code"] == "DELAY_EXPLANATION_REQUIRED" and r.json()["details"]["why"] == "none_submitted"
    r = do(client, as_user, "abc", t["id"], "submit-for-review", FINISH)
    assert r.status_code == 409 and r.json()["code"] == "DELAY_EXPLANATION_REQUIRED"
    assert detail(client, as_user, t["id"])["status"] == "in_progress"


def test_a_one_line_reason_while_finishing_is_recorded_as_an_explanation(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    d = ok(client, as_user, "abc", t["id"], "complete", FINISH | {"late_reason": "Waited for the client's content for two days"})
    assert d["status"] == "under_review" and len(d["delay"]["items"]) == 1  # ADR 008: finishing goes to review
    e = d["delay"]["items"][0]
    assert e["reason"].startswith("Waited for the client") and e["progress_pct"] == 100 and e["kind"] == "initial"
    done = approve_through(client, as_user, t["id"])
    assert done["status"] == "completed" and done["completed_at"] > done["due_at"]  # completed after the deadline


def test_finishing_after_a_normal_explanation_needs_no_extra_reason(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    assert ok(client, as_user, "abc", t["id"], "complete", FINISH)["status"] == "under_review"


def test_waiting_for_review_is_not_the_employees_delay(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    d = ok(client, as_user, "abc", t["id"], "submit-for-review", FINISH | {"late_reason": "Delivered late because of the vendor delay"})
    assert d["status"] == "under_review" and d["delay"]["required"] is False and d["delay"]["overdue"] is False


# ---------------------------------------------------------------- manager decisions


def test_accepting_an_explanation_does_not_complete_the_task(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    rid = explain(client, as_user, t["id"]).json()["delay"]["items"][0]["id"]
    assert review(client, as_user, rid, "accepted", who="abc").status_code == 403  # not the employee's call
    r = review(client, as_user, rid, "accepted", comment="Understood, finish it by Friday")
    assert r.status_code == 200
    d = r.json()["task"]
    assert d["status"] == "in_progress" and d["is_overdue"] is True and d["completed_at"] is None  # still open and overdue
    assert d["delay"]["required"] is False and d["delay"]["latest_decision"] == "accepted" and d["delay"]["awaiting_review"] is False
    assert d["delay"]["items"][0]["reviews"][0]["by"] == "Demo Manager"


@pytest.mark.parametrize("decision", ["clarification_requested", "rejected"])
def test_asking_for_more_or_rejecting_requires_a_newer_explanation(client, as_user, seeded, decision):
    t = overdue_task(client, as_user, seeded)
    rid = explain(client, as_user, t["id"]).json()["delay"]["items"][0]["id"]
    assert review(client, as_user, rid, decision).json()["code"] == "COMMENT_REQUIRED"  # must say what is needed
    d = review(client, as_user, rid, decision, comment="Which parts are still missing, exactly?").json()["task"]
    assert d["delay"]["required"] is True and d["delay"]["why"] == "needs_update"  # the requirement is back
    assert do(client, as_user, "abc", t["id"], "complete", FINISH).json()["code"] == "DELAY_EXPLANATION_REQUIRED"
    d = explain(client, as_user, t["id"], reason="Remaining: reporting endpoints and the admin screens").json()
    assert d["delay"]["required"] is False and d["delay"]["awaiting_review"] is True


def test_only_the_latest_explanation_can_be_reviewed(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    first = explain(client, as_user, t["id"]).json()["delay"]["items"][0]["id"]
    explain(client, as_user, t["id"], reason="Update: now waiting only on test data", progress_pct=80)
    r = review(client, as_user, first, "accepted")
    assert r.status_code == 409 and r.json()["code"] == "SUPERSEDED"


def test_review_scope_and_self_review(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    rid = explain(client, as_user, t["id"]).json()["delay"]["items"][0]["id"]
    assert review(client, as_user, rid, "accepted", who="hrhead").status_code == 404  # another department
    assert review(client, as_user, rid, "accepted", who="devhead").status_code == 200  # their own department
    own = overdue_task(client, as_user, seeded, assignee="EMP-0004", worker="devhead", title="Head's own task")
    rid2 = explain(client, as_user, own["id"], who="devhead").json()["delay"]["items"][0]["id"]
    assert review(client, as_user, rid2, "accepted", who="devhead").status_code == 403  # nobody reviews themselves
    assert review(client, as_user, rid2, "accepted", who="manager").status_code == 200


def test_escalating_is_recorded(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    rid = explain(client, as_user, t["id"]).json()["delay"]["items"][0]["id"]
    d = review(client, as_user, rid, "escalated", who="devhead", comment="Needs the CEO's attention").json()["task"]
    assert d["delay"]["latest_decision"] == "escalated" and d["delay"]["items"][0]["reviews"][0]["decision"] == "escalated"
    assert "DELAY_REVIEWED" in [e["action"] for e in client.get(f"{API}/tasks/{t['id']}/timeline", headers=as_user("owner")).json()]


def test_approving_a_revised_deadline_resets_the_clock_and_the_requirement(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    rid = explain(client, as_user, t["id"]).json()["delay"]["items"][0]["id"]
    new = str(clock.utcnow().date() + timedelta(days=4))
    assert review(client, as_user, rid, "revised_deadline_approved").json()["code"] == "DEADLINE_REQUIRED"
    r = review(client, as_user, rid, "revised_deadline_approved", due_date=new, comment="Agreed: new date is Friday EOD")
    assert r.status_code == 200
    d = r.json()["task"]
    assert d["is_overdue"] is False and d["deadline"]["version"] == 2 and d["deadline"]["extension_count"] == 1
    assert d["deadline"]["history"][-1]["reason"] == "Agreed: new date is Friday EOD" and d["original_due_at"] == t["original_due_at"]
    # the revised deadline is missed too: a NEW explanation is required for the NEW deadline
    clock.freeze(datetime.fromisoformat(d["due_at"].rstrip("Z")) + timedelta(hours=3))
    again = detail(client, as_user, t["id"])
    assert again["is_overdue"] is True and again["delay"]["required"] is True and again["delay"]["why"] == "none_submitted"
    assert len(again["delay"]["items"]) == 1  # the earlier explanation is kept as history, but does not count
    assert review(client, as_user, rid, "accepted").json()["code"] in ("OBSOLETE", "SUPERSEDED")


def test_a_stale_explanation_must_be_refreshed_but_an_accepted_one_need_not(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    clock.freeze(clock.utcnow() + timedelta(days=3, hours=1))
    d = detail(client, as_user, t["id"])
    assert d["delay"]["required"] is True and d["delay"]["why"] == "stale"  # three days with no news and still overdue
    accepted = overdue_task(client, as_user, seeded, start=False, title="Accepted one")  # (time only moves forward)
    rid = explain(client, as_user, accepted["id"]).json()["delay"]["items"][0]["id"]
    review(client, as_user, rid, "accepted")
    clock.freeze(clock.utcnow() + timedelta(days=5))
    assert detail(client, as_user, accepted["id"])["delay"]["required"] is False


# ---------------------------------------------------------------- the manager's queue


def test_manager_queue_lists_missing_and_awaiting_review(client, as_user, seeded):
    at(0)
    make(client, as_user, seeded, title="Silent employee task")
    spoke = make(client, as_user, seeded, title="Explained task")
    due = datetime.fromisoformat(spoke["due_at"].rstrip("Z"))
    clock.freeze(due + timedelta(days=1))  # both deadlines have now passed
    explain(client, as_user, spoke["id"])
    for who in ("devhead", "manager"):
        q = client.get(f"{API}/delays/queue", headers=as_user(who)).json()
        assert [m["title"] for m in q["missing"]] == ["Silent employee task"] and q["missing"][0]["why"] == "none_submitted", who
        assert [a["title"] for a in q["awaiting"]] == ["Explained task"] and q["awaiting"][0]["explanation"]["reason"], who
    for who in ("owner", "ceo"):  # nothing escalated to them yet
        assert client.get(f"{API}/delays/queue", headers=as_user(who)).json() == {"missing": [], "awaiting": []}, who
    assert client.get(f"{API}/delays/queue", headers=as_user("hrhead")).json() == {"missing": [], "awaiting": []}  # another department
    for who in ("abc", "admin"):
        assert client.get(f"{API}/delays/queue", headers=as_user(who)).status_code == 403


# ---------------------------------------------------------------- escalation tiers count WORKING days


def test_escalation_tiers_skip_sundays_and_off_saturdays(db):
    # Friday 13 Nov 2026 18:30 IST. Sat 14 (2nd Saturday) and Sun 15 are off, so +1 working day is Monday 16.
    due = datetime(2026, 11, 13, 13, 0)
    tiers = escalation_times(db, due)
    assert [(lvl, code) for lvl, code, _ in tiers] == [(1, "after_1d"), (2, "after_3d"), (3, "after_7d")]
    assert [when for _l, _c, when in tiers] == [datetime(2026, 11, 16, 13, 0), datetime(2026, 11, 18, 13, 0), datetime(2026, 11, 23, 13, 0)]


def test_escalation_level_over_time(db):
    due = datetime(2026, 11, 13, 13, 0)
    assert escalation_level(db, due, datetime(2026, 11, 13, 12, 0)) == 0  # not overdue yet
    assert escalation_level(db, due, datetime(2026, 11, 13, 14, 0)) == 0  # overdue, but no tier reached
    assert escalation_level(db, due, datetime(2026, 11, 15, 13, 0)) == 0  # Sunday: no working day has passed
    assert escalation_level(db, due, datetime(2026, 11, 16, 13, 0)) == 1
    assert escalation_level(db, due, datetime(2026, 11, 18, 13, 0)) == 2
    assert escalation_level(db, due, datetime(2026, 11, 23, 12, 59)) == 2
    assert escalation_level(db, due, datetime(2026, 11, 23, 13, 0)) == 3


def test_escalation_level_is_visible_on_the_task(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded, late_days=9)
    assert detail(client, as_user, t["id"], "owner")["delay"]["escalation_level"] >= 2
    assert client.get(f"{API}/tasks", headers=as_user("owner")).json()["items"][0]["escalation_level"] >= 2


_ = date


# ---------------------------------------------------------------- the reason reaches CEO / Owner only after the line approves it


def test_leadership_sees_the_reason_only_after_head_or_manager_approves(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    r = explain(client, as_user, t["id"])
    rid = detail(client, as_user, t["id"])["delay"]["items"][0]["id"]
    assert r.status_code == 201
    for who in ("owner", "ceo"):
        d = detail(client, as_user, t["id"], who)
        assert d["delay"]["items"] == [] and "review_delay" not in d["allowed_actions"], who
        assert review(client, as_user, rid, "accepted", who=who).status_code == 404  # cannot approve what they cannot see
    assert review(client, as_user, rid, "accepted", who="devhead").status_code == 200  # the Department Head approves
    for who in ("owner", "ceo"):
        items = detail(client, as_user, t["id"], who)["delay"]["items"]
        assert len(items) == 1 and items[0]["reviews"][0]["decision"] == "accepted", who


def test_clarification_or_rejection_never_reaches_leadership(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    rid = detail(client, as_user, t["id"])["delay"]["items"][0]["id"]
    assert review(client, as_user, rid, "rejected", who="manager", comment="This is not a real reason").status_code == 200
    assert detail(client, as_user, t["id"], "owner")["delay"]["items"] == []
    assert detail(client, as_user, t["id"], "ceo")["delay"]["items"] == []


def test_escalation_hands_the_decision_to_leadership(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    rid = detail(client, as_user, t["id"])["delay"]["items"][0]["id"]
    assert review(client, as_user, rid, "escalated", who="manager", comment="Needs your call").status_code == 200
    q = client.get(f"{API}/delays/queue", headers=as_user("ceo")).json()
    assert [a["title"] for a in q["awaiting"]] == [t["title"]]
    d = detail(client, as_user, t["id"], "ceo")
    assert d["delay"]["items"] and "review_delay" in d["allowed_actions"]
    assert review(client, as_user, rid, "accepted", who="ceo").status_code == 200


def test_manager_can_approve_for_a_head_less_department(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded, assignee="EMP-0011", worker="support1")  # Support reports straight to the Manager
    explain(client, as_user, t["id"], who="support1")
    rid = detail(client, as_user, t["id"], "support1")["delay"]["items"][0]["id"]
    assert detail(client, as_user, t["id"], "owner")["delay"]["items"] == []
    assert review(client, as_user, rid, "accepted", who="manager").status_code == 200
    assert len(detail(client, as_user, t["id"], "owner")["delay"]["items"]) == 1
