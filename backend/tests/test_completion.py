"""Phase 4: progress, finishing work with an assurance, optional review, verify, and revert (e.g. QA finds a defect)."""

from .helpers import API, FINISH, approve_through, at, complete_fully, do, make, ok


def work(client, as_user, tid, minutes=60, start=0, who="abc"):
    """Start, work for `minutes`, stop (the task stays in progress)."""
    at(start)
    ok(client, as_user, who, tid, "start")
    at(start + minutes)
    ok(client, as_user, who, tid, "stop")
    return start + minutes


def started_task(client, as_user, seeded, assignee="EMP-0007", who="abc", **over):
    at(0)
    t = make(client, as_user, seeded, assignee=assignee, **over)
    ok(client, as_user, who, t["id"], "start")
    return t


# ---------------------------------------------------------------- progress


def test_progress_updates_are_recorded_and_visible(client, as_user, seeded):
    t = started_task(client, as_user, seeded)
    at(30)
    d = ok(client, as_user, "abc", t["id"], "progress", {"progress_pct": 40, "note": "Auth module done"})
    assert d["progress_pct"] == 40 and d["updates"][0]["note"] == "Auth module done"
    at(60)
    d = ok(client, as_user, "abc", t["id"], "progress", {"progress_pct": 70, "note": "Endpoints wired up"})
    assert [u["progress_pct"] for u in d["updates"]] == [70, 40]  # newest first, nothing overwritten
    tl = [e["action"] for e in client.get(f"{API}/tasks/{t['id']}/timeline", headers=as_user("owner")).json()]
    assert tl.count("TASK_PROGRESS") == 2


def test_progress_rules(client, as_user, seeded):
    at(0)
    fresh = make(client, as_user, seeded)
    assert do(client, as_user, "abc", fresh["id"], "progress", {"progress_pct": 10, "note": "Not started yet"}).status_code == 409
    t = started_task(client, as_user, seeded, title="Another task")
    assert do(client, as_user, "abc", t["id"], "progress", {"progress_pct": 101, "note": "Too much"}).status_code == 422
    assert do(client, as_user, "abc", t["id"], "progress", {"progress_pct": 50, "note": "x"}).status_code == 422
    assert do(client, as_user, "owner", t["id"], "progress", {"progress_pct": 50, "note": "Owner says so"}).status_code == 403


# ---------------------------------------------------------------- finishing: employee marks it done with an assurance


def test_employee_completes_their_own_task_with_an_assurance(client, as_user, seeded):
    t = started_task(client, as_user, seeded)
    at(60)
    d = ok(client, as_user, "abc", t["id"], "complete", FINISH | {"test_notes": "Unit and manual tests passed", "evidence_url": "https://ci.example.com/run/42"})
    assert d["status"] == "under_review" and d["progress_pct"] == 100 and d["timer_running"] is False  # ADR 008: finishing sends it to review
    assert d["time"]["sessions"][0]["end_reason"] == "completed" and d["time"]["active_seconds"] == 3600  # the running timer stopped
    a = d["assurances"][0]
    assert a["attempt"] == 1 and a["tested"] is True and a["evidence_url"] == "https://ci.example.com/run/42"
    assert d["allowed_actions"] == []  # the employee cannot change anything after completing
    assert d["revert_count"] == 0 and d["verified_at"] is None
    done = approve_through(client, as_user, t["id"])  # head, then CEO/Owner
    assert done["status"] == "completed" and done["completed_at"] and done["verified_at"]


def test_completion_needs_tracked_time_or_an_explanation(client, as_user, seeded):
    t = started_task(client, as_user, seeded)  # started and finished in the same instant: 0 seconds tracked
    r = do(client, as_user, "abc", t["id"], "complete", FINISH)
    assert r.status_code == 422 and r.json()["code"] == "TIME_REQUIRED"
    d = ok(client, as_user, "abc", t["id"], "complete", FINISH | {"no_time_reason": "Configuration change, done in minutes"})
    assert d["status"] == "under_review" and d["assurances"][0]["no_time_reason"].startswith("Configuration")


def test_not_tested_requires_an_explanation(client, as_user, seeded):
    t = started_task(client, as_user, seeded)
    at(60)
    r = do(client, as_user, "abc", t["id"], "complete", {"summary": "Done, QA will test it", "tested": False})
    assert r.status_code == 422 and r.json()["code"] == "TEST_NOTES_REQUIRED"
    d = ok(client, as_user, "abc", t["id"], "complete", {"summary": "Done, QA will test it", "tested": False, "test_notes": "No test environment yet"})
    assert d["assurances"][0]["tested"] is False


def test_completion_guards(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    assert do(client, as_user, "abc", t["id"], "complete", FINISH).json()["code"] == "NOT_IN_PROGRESS"  # must start first
    ok(client, as_user, "abc", t["id"], "start")
    at(60)
    assert do(client, as_user, "owner", t["id"], "complete", FINISH).status_code == 403  # only the assignee finishes it
    assert do(client, as_user, "devhead", t["id"], "complete", FINISH).status_code == 403
    assert do(client, as_user, "abc", t["id"], "complete", {"summary": "ok", "tested": True}).status_code == 422
    bad = do(client, as_user, "abc", t["id"], "complete", FINISH | {"evidence_url": "javascript:alert(1)"})
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_EVIDENCE_URL"
    assert do(client, as_user, "abc", t["id"], "complete", FINISH | {"unexpected": 1}).status_code == 422  # no mass assignment
    assert ok(client, as_user, "abc", t["id"], "complete", FINISH)["status"] == "under_review"
    assert do(client, as_user, "abc", t["id"], "complete", FINISH).status_code == 409  # not twice


def test_cannot_complete_while_on_hold(client, as_user, seeded):
    t = started_task(client, as_user, seeded)
    at(30)
    ok(client, as_user, "abc", t["id"], "hold", {"reason": "Waiting for access"})
    assert do(client, as_user, "abc", t["id"], "complete", FINISH).status_code == 409


# ---------------------------------------------------------------- optional review


def review_type(client, as_user):
    meta = client.get(f"{API}/task-meta", headers=as_user("owner")).json()
    return next(x["id"] for x in meta["types"] if x["requires_review"])


def test_review_required_tasks_go_through_a_reviewer(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, type_id=review_type(client, as_user))
    ok(client, as_user, "abc", t["id"], "start")
    at(60)
    d = ok(client, as_user, "abc", t["id"], "complete", FINISH)  # ADR 008: finishing always goes to review; "submit" is the same step
    assert d["status"] == "under_review" and d["submitted_at"] and d["allowed_actions"] == []
    assert "review" in client.get(f"{API}/tasks/{t['id']}", headers=as_user("devhead")).json()["allowed_actions"]
    assert do(client, as_user, "abc", t["id"], "review", {"decision": "approve"}).status_code == 403  # not their call
    head_ok = ok(client, as_user, "devhead", t["id"], "review", {"decision": "approve", "comment": "Looks good"})
    assert head_ok["status"] == "under_review" and head_ok["review_stage"] == "leadership"  # the head passes it up
    approved = ok(client, as_user, "owner", t["id"], "review", {"decision": "approve"})
    assert approved["status"] == "completed" and approved["verified_at"] and approved["completed_at"]


def test_review_rejection_sends_it_back_with_a_reason(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, type_id=review_type(client, as_user))
    ok(client, as_user, "abc", t["id"], "start")
    at(60)
    ok(client, as_user, "abc", t["id"], "submit-for-review", FINISH)
    assert do(client, as_user, "devhead", t["id"], "review", {"decision": "reject"}).status_code == 422  # must say what to fix
    d = ok(client, as_user, "devhead", t["id"], "review", {"decision": "reject", "reason_code": "incomplete", "comment": "Error handling is missing"})
    assert d["status"] == "reopened" and d["revert_count"] == 1 and d["reverts"][0]["reason"] == "Error handling is missing"
    assert d["verified_at"] is None and d["submitted_at"] is None


def test_submitting_for_review_is_allowed_even_when_not_required(client, as_user, seeded):
    t = started_task(client, as_user, seeded)
    at(60)
    assert ok(client, as_user, "abc", t["id"], "submit-for-review", FINISH)["status"] == "under_review"


def test_you_cannot_review_your_own_submission(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, who="owner", assignee="EMP-0004", type_id=review_type(client, as_user))  # task for the Dev Head
    ok(client, as_user, "devhead", t["id"], "start")
    at(60)
    ok(client, as_user, "devhead", t["id"], "submit-for-review", FINISH)
    assert do(client, as_user, "devhead", t["id"], "review", {"decision": "approve"}).status_code == 403
    assert ok(client, as_user, "owner", t["id"], "review", {"decision": "approve"})["status"] == "completed"  # head's own work: straight to CEO/Owner


# ---------------------------------------------------------------- verify (optional) and revert (QA finds a defect)


def completed(client, as_user, seeded, **over):
    t = started_task(client, as_user, seeded, **over)
    at(60)
    complete_fully(client, as_user, "abc", t["id"])
    return t


def test_manager_can_verify_a_completed_task_once(client, as_user, seeded):
    t = completed(client, as_user, seeded)
    # ADR 008: work that went through the review chain is verified by the CEO/Owner's approval; verifying again is refused
    d = client.get(f"{API}/tasks/{t['id']}", headers=as_user("devhead")).json()
    assert d["verified_at"] and "verify" not in d["allowed_actions"] and "revert" in d["allowed_actions"]
    assert do(client, as_user, "abc", t["id"], "verify").status_code == 403
    assert do(client, as_user, "hrhead", t["id"], "verify").status_code == 404  # another department
    assert do(client, as_user, "devhead", t["id"], "verify").json()["code"] == "ALREADY_VERIFIED"


def test_cannot_verify_work_that_is_not_completed(client, as_user, seeded):
    t = started_task(client, as_user, seeded)
    assert do(client, as_user, "devhead", t["id"], "verify").json()["code"] == "NOT_COMPLETED"


def test_nobody_verifies_their_own_work(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, who="owner", assignee="EMP-0004")  # assigned to the Developers Head
    ok(client, as_user, "devhead", t["id"], "start")
    at(60)
    ok(client, as_user, "devhead", t["id"], "complete", FINISH)
    assert do(client, as_user, "devhead", t["id"], "verify").status_code in (403, 409)
    assert do(client, as_user, "devhead", t["id"], "revert", {"reason_code": "other", "reason": "Reverting my own work"}).status_code in (403, 409)
    assert approve_through(client, as_user, t["id"])["verified_at"]  # the CEO/Owner signs it off


def test_qa_finds_a_defect_and_the_task_is_reverted(client, as_user, seeded):
    t = completed(client, as_user, seeded)
    assert do(client, as_user, "abc", t["id"], "revert", {"reason_code": "qa_defect", "reason": "Login fails"}).status_code == 403
    assert do(client, as_user, "devhead", t["id"], "revert", {"reason_code": "qa_defect", "reason": "x"}).status_code == 422
    assert do(client, as_user, "devhead", t["id"], "revert", {"reason_code": "typo", "reason": "Login fails on Safari"}).status_code == 422
    d = ok(client, as_user, "devhead", t["id"], "revert", {"reason_code": "qa_defect", "reason": "Login fails on Safari", "found_by": "QA"})
    assert d["status"] == "reopened" and d["revert_count"] == 1
    assert d["completed_at"] is None and d["verified_at"] is None  # it is no longer finished or verified
    assert d["reverts"] == [{"attempt": 1, "reason_code": "qa_defect", "reason": "Login fails on Safari", "found_by": "QA", "at": d["reverts"][0]["at"]}]
    mine = client.get(f"{API}/tasks/{t['id']}", headers=as_user("abc")).json()
    assert "start" in mine["allowed_actions"] and "acknowledge" not in mine["allowed_actions"]  # the employee can pick it up again


def test_employee_fixes_it_and_completes_again_with_a_new_attempt(client, as_user, seeded):
    t = completed(client, as_user, seeded)
    ok(client, as_user, "devhead", t["id"], "revert", {"reason_code": "qa_defect", "reason": "Login fails on Safari", "found_by": "QA"})
    at(120)
    ok(client, as_user, "abc", t["id"], "start")
    at(180)
    ok(client, as_user, "abc", t["id"], "complete", FINISH | {"summary": "Fixed the Safari login issue"})
    d = approve_through(client, as_user, t["id"])
    assert d["status"] == "completed" and [a["attempt"] for a in d["assurances"]] == [1, 2] and d["revert_count"] == 1
    assert d["time"]["active_seconds"] == 2 * 3600  # both rounds of work are counted
    again = ok(client, as_user, "owner", t["id"], "revert", {"reason_code": "requirement_change", "reason": "Client changed the login flow"})
    assert again["revert_count"] == 2 and again["reverts"][1]["attempt"] == 2 and again["reverts"][1]["reason_code"] == "requirement_change"


def test_revert_only_applies_to_completed_work_and_within_scope(client, as_user, seeded):
    t = started_task(client, as_user, seeded)
    r = do(client, as_user, "devhead", t["id"], "revert", {"reason_code": "other", "reason": "Not finished yet"})
    assert r.status_code == 409 and r.json()["code"] == "INVALID_TRANSITION"
    at(60)
    complete_fully(client, as_user, "abc", t["id"])
    assert do(client, as_user, "hrhead", t["id"], "revert", {"reason_code": "other", "reason": "Not their department"}).status_code == 404
    for who in ("owner", "ceo", "manager"):  # everyone above can send it back
        assert "revert" in client.get(f"{API}/tasks/{t['id']}", headers=as_user(who)).json()["allowed_actions"]


def test_reverts_are_counted_as_rework_in_the_trail(client, as_user, seeded):
    t = completed(client, as_user, seeded)
    ok(client, as_user, "devhead", t["id"], "revert", {"reason_code": "incomplete", "reason": "Missing documentation"})
    actions = [e["action"] for e in client.get(f"{API}/tasks/{t['id']}/timeline", headers=as_user("owner")).json()]
    assert actions[:3] == ["TASK_CREATED", "TASK_STARTED", "TIMER_STARTED"] and "TASK_SUBMITTED" in actions and actions[-1] == "TASK_REVERTED"
    hist = [(h["from"], h["to"]) for h in client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()["status_history"]]
    assert hist == [(None, "assigned"), ("assigned", "in_progress"), ("in_progress", "under_review"), ("under_review", "completed"), ("completed", "reopened")]
