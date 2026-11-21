"""Phase 4: the timer (one at a time, server time only), forgotten timers, missing time and corrections."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.timetracking.guard import run_guard
from app.modules.timetracking.models import TimeCorrection, TimeLog, TimerCheckin

from .helpers import ABC, API, BASE, FE, at, do, eid, make, ok

# ---------------------------------------------------------------- starting, pausing, stopping


def test_start_moves_task_to_in_progress_and_runs_the_timer(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    d = ok(client, as_user, "abc", t["id"], "start")
    assert d["status"] == "in_progress" and d["timer_running"] is True
    assert {"pause", "stop", "progress", "hold", "complete"} <= set(d["allowed_actions"]) and "start" not in d["allowed_actions"]
    a = client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"]
    assert a["task"]["id"] == t["id"] and a["elapsed_seconds"] == 0
    at(90)
    a = client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"]
    assert a["elapsed_seconds"] == 90 * 60  # the SERVER measures time; nothing comes from the browser


def test_only_the_assignee_can_run_the_timer(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    assert do(client, as_user, "owner", t["id"], "start").status_code == 403  # the Owner can see it, not work it
    assert do(client, as_user, "devhead", t["id"], "start").status_code == 403
    assert do(client, as_user, "hrhead", t["id"], "start").status_code == 404  # outside their scope


def test_timer_state_survives_a_page_refresh_or_new_login(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(30)
    again = client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"]  # brand-new login = like a refresh
    assert again["task"]["id"] == t["id"] and again["elapsed_seconds"] == 30 * 60


def test_second_timer_is_refused_until_you_switch(client, as_user, seeded):
    at(0)
    a, b = make(client, as_user, seeded, title="Task A"), make(client, as_user, seeded, title="Task B")
    ok(client, as_user, "abc", a["id"], "start")
    again = do(client, as_user, "abc", a["id"], "start")
    assert again.status_code == 409 and again.json()["code"] == "TIMER_ALREADY_ACTIVE"
    other = do(client, as_user, "abc", b["id"], "start")
    assert other.status_code == 409 and other.json()["details"]["task_no"] == a["task_no"]  # tells you where it is running
    at(60)
    ok(client, as_user, "abc", b["id"], "start", {"switch": True})
    sessions = client.get(f"{API}/tasks/{a['id']}/time", headers=as_user("abc")).json()["sessions"]
    assert sessions[0]["end_reason"] == "switched" and sessions[0]["seconds"] == 3600 and not sessions[0]["running"]
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"]["task"]["id"] == b["id"]
    assert client.get(f"{API}/tasks/{a['id']}", headers=as_user("abc")).json()["status"] == "in_progress"  # not lost


def test_database_itself_refuses_two_open_timers(client, as_user, seeded):
    at(0)
    a, b = make(client, as_user, seeded, title="Task A"), make(client, as_user, seeded, title="Task B")
    ok(client, as_user, "abc", a["id"], "start")
    with seeded() as s:
        s.add(TimeLog(task_id=b["id"], employee_id=a["assignee"]["id"], started_at=BASE, source="timer"))
        with pytest.raises(IntegrityError):
            s.flush()  # the unique key on the generated 'active' column is the last line of defence


def test_the_spec_example_three_sessions_add_up_to_nine_hours(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, estimated_hours=12)
    tid = t["id"]
    ok(client, as_user, "abc", tid, "start")
    at(120)
    ok(client, as_user, "abc", tid, "pause")  # session 1: 2 h
    at(180)
    ok(client, as_user, "abc", tid, "start")  # resume
    at(360)
    ok(client, as_user, "abc", tid, "stop")  # session 2: 3 h
    at(400)
    ok(client, as_user, "abc", tid, "start")
    at(640)
    d = ok(client, as_user, "abc", tid, "stop")  # session 3: 4 h
    tm = d["time"]
    assert tm["active_seconds"] == 9 * 3600 and tm["remaining_seconds"] == 3 * 3600 and tm["estimated_seconds"] == 12 * 3600
    assert [s["seconds"] for s in tm["sessions"]] == [7200, 10800, 14400]
    assert [s["end_reason"] for s in tm["sessions"]] == ["paused", "stopped", "stopped"]
    assert tm["elapsed_seconds"] == 640 * 60 and tm["assign_to_start_seconds"] == 0 and tm["running"] is False


def test_assignment_to_start_latency_and_elapsed_are_tracked(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    at(45)
    d = ok(client, as_user, "abc", t["id"], "start")
    assert d["time"]["assign_to_start_seconds"] == 45 * 60
    at(165)
    assert client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()["elapsed_seconds"] == 165 * 60


def test_pause_without_a_running_timer_is_an_error(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    r = do(client, as_user, "abc", t["id"], "pause")
    assert r.status_code == 409 and r.json()["code"] == "NO_ACTIVE_TIMER"


def test_hold_stops_the_clock_and_blocks_starting(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(60)
    assert do(client, as_user, "abc", t["id"], "hold", {"reason": "x"}).status_code == 422
    d = ok(client, as_user, "abc", t["id"], "hold", {"reason": "Waiting for the client's API keys"})
    assert d["status"] == "on_hold" and d["timer_running"] is False and d["time"]["active_seconds"] == 3600
    assert do(client, as_user, "abc", t["id"], "start").json()["code"] == "TASK_NOT_STARTABLE"
    assert ok(client, as_user, "abc", t["id"], "unhold")["status"] == "in_progress"
    assert ok(client, as_user, "abc", t["id"], "start")["timer_running"] is True  # work resumes explicitly


def test_manager_can_hold_a_task_and_it_stops_the_assignees_timer(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(30)
    d = ok(client, as_user, "devhead", t["id"], "hold", {"reason": "Priorities changed"})
    assert d["status"] == "on_hold" and d["time"]["active_seconds"] == 1800
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"] is None


def test_cancelling_or_reassigning_stops_the_running_timer(client, as_user, seeded):
    at(0)
    a, b = make(client, as_user, seeded, title="Task A"), make(client, as_user, seeded, title="Task B")
    ok(client, as_user, "abc", a["id"], "start")
    at(20)
    ok(client, as_user, "owner", a["id"], "cancel", {"reason": "No longer required"})
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"] is None
    ok(client, as_user, "abc", b["id"], "start")
    at(50)
    ok(client, as_user, "devhead", b["id"], "reassign", {"assignee_id": eid(seeded, FE)})  # -> Frontend Dev
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"] is None
    with seeded() as s:
        reasons = [lg.end_reason for lg in s.scalars(select(TimeLog).order_by(TimeLog.id))]
    assert reasons == ["cancelled", "reassigned"]


# ---------------------------------------------------------------- forgotten timers


def test_timer_is_closed_at_ten_hours_and_flagged_provisional(client, as_user, seeded):
    at(0)  # 09:30 IST
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(11 * 60)  # nobody stopped it; it is now 20:30 IST
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"] is None  # enforced on first contact
    sessions = client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()
    s = sessions["sessions"][0]
    assert s["seconds"] == 10 * 3600 and s["source"] == "auto_closed" and s["end_reason"] == "auto_timeout" and s["confirmed"] is False
    assert sessions["provisional_seconds"] == 10 * 3600 and sessions["active_seconds"] == 10 * 3600  # counted, but flagged


def test_running_session_never_counts_past_its_cap_even_before_any_job_runs(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(30 * 60)  # a day and a half later, nobody touched anything
    tm = client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("owner")).json()
    assert tm["active_seconds"] == 10 * 3600  # capped, not 30 hours


def test_evening_cutoff_closes_a_late_timer_at_2200_company_time(client, as_user, seeded):
    at(5 * 60)  # 14:30 IST
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(5 * 60 + 8 * 60)  # 22:30 IST: past the 22:00 cut-off
    client.get(f"{API}/time/active", headers=as_user("abc"))  # first contact closes the forgotten timer
    s = client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()["sessions"][0]
    assert s["seconds"] == int(7.5 * 3600) and s["source"] == "auto_closed"  # 14:30 -> 22:00 IST


def test_checkins_after_4h_8h_and_evening_are_created_once(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    with seeded() as s:
        at(4 * 60 + 5)
        assert run_guard(s)["checkins_created"] == 1  # after 4 h
        s.commit()
        assert run_guard(s)["checkins_created"] == 0  # running the job again changes nothing
        at(8 * 60 + 5)  # 17:35 IST
        assert run_guard(s)["checkins_created"] == 1  # after 8 h
        s.commit()
        kinds = sorted(c.kind for c in s.scalars(select(TimerCheckin)))
        assert kinds == ["after_4h", "after_8h"]
    a = client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"]
    assert a["checkin"]["kind"] == "after_8h"  # the page shows the latest 'Still working?' prompt


def test_evening_checkin_when_still_running_after_closing_time(client, as_user, seeded):
    at(4 * 60)  # 13:30 IST
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    with seeded() as s:
        at(9 * 60 + 45)  # 19:15 IST: after 19:00
        run_guard(s)
        s.commit()
        assert "evening" in {c.kind for c in s.scalars(select(TimerCheckin))}


def test_continue_resets_the_continuous_clock_and_extends_the_cap(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    with seeded() as s:
        at(8 * 60 + 5)
        run_guard(s)
        s.commit()
    assert client.post(f"{API}/time/checkin/continue", headers=as_user("abc")).status_code == 200
    a = client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"]
    assert a["checkin"] is None  # answered
    at(8 * 60 + 5 + 150)  # 20:05 IST: without 'Continue' the 10 h cap (19:30) would have closed it; with it, still running
    assert client.get(f"{API}/time/active", headers=as_user("abc")).json()["active"] is not None


def test_stopping_a_session_answers_its_checkins(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    with seeded() as s:
        at(4 * 60 + 5)
        run_guard(s)
        s.commit()
    ok(client, as_user, "abc", t["id"], "stop")
    with seeded() as s:
        c = s.scalar(select(TimerCheckin))
        assert c.response == "stop" and c.responded_at is not None


def test_employee_can_shorten_an_auto_closed_session_but_not_extend_it(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    client.post(f"{API}/time/heartbeat", headers=as_user("abc"))  # app open at 09:30
    at(120)
    client.post(f"{API}/time/heartbeat", headers=as_user("abc"))  # last seen at 11:30 IST
    at(12 * 60)
    pending = client.get(f"{API}/time/unconfirmed", headers=as_user("abc")).json()
    assert pending == []  # nothing is closed yet: reading /time/unconfirmed does not run the guard...
    client.get(f"{API}/time/active", headers=as_user("abc"))  # ...but the first contact does
    pending = client.get(f"{API}/time/unconfirmed", headers=as_user("abc")).json()
    assert len(pending) == 1 and pending[0]["seconds"] == 10 * 3600
    assert pending[0]["suggested_end"] == (BASE + timedelta(minutes=120)).isoformat() + "Z"  # last time the app was seen
    log_id = pending[0]["id"]
    longer = (BASE + timedelta(hours=11)).isoformat() + "Z"
    r = client.post(f"{API}/time/logs/{log_id}/confirm", headers=as_user("abc"), json={"ended_at": longer})
    assert r.status_code == 422 and r.json()["code"] == "EXTENSION_NEEDS_APPROVAL"
    r = client.post(f"{API}/time/logs/{log_id}/confirm", headers=as_user("abc"), json={"ended_at": pending[0]["suggested_end"]})
    assert r.status_code == 200 and r.json()["seconds"] == 2 * 3600 and r.json()["confirmed"] is True
    assert client.get(f"{API}/time/unconfirmed", headers=as_user("abc")).json() == []
    with seeded() as s:
        corr = s.scalar(select(TimeCorrection))
        assert corr.kind == "trim" and corr.old_ended_at > corr.new_ended_at  # the original end is preserved


def test_confirming_as_is_and_other_peoples_sessions(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(12 * 60)
    client.get(f"{API}/time/active", headers=as_user("abc"))
    log_id = client.get(f"{API}/time/unconfirmed", headers=as_user("abc")).json()[0]["id"]
    assert client.post(f"{API}/time/logs/{log_id}/confirm", headers=as_user("frontend"), json={}).status_code == 404
    assert client.post(f"{API}/time/logs/{log_id}/confirm", headers=as_user("abc"), json={}).status_code == 200
    assert client.post(f"{API}/time/logs/{log_id}/confirm", headers=as_user("abc"), json={}).status_code == 409


def test_admin_can_run_the_guard_on_demand(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(12 * 60)
    assert client.post(f"{API}/admin/jobs/timer-guard", headers=as_user("ceo")).status_code == 403
    r = client.post(f"{API}/admin/jobs/timer-guard", headers=as_user("admin"))
    assert r.status_code == 200 and r.json()["auto_closed"] == 1
    r2 = client.post(f"{API}/admin/jobs/timer-guard", headers=as_user("owner"))
    assert r2.status_code == 200 and r2.json()["auto_closed"] == 0


# ---------------------------------------------------------------- missing time and corrections


def iso(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat() + "Z"


def missing(client, as_user, tid, start, end, reason="Forgot to start the timer", who="abc"):
    return client.post(f"{API}/time/corrections", headers=as_user(who),
                       json={"task_id": tid, "started_at": iso(start), "ended_at": iso(end), "reason": reason})  # fmt: skip


def test_missing_time_is_requested_then_approved_by_a_manager(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    at(24 * 60)  # next day
    r = missing(client, as_user, t["id"], 60, 180)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()["active_seconds"] == 0  # never applied silently
    queue = client.get(f"{API}/time/corrections", headers=as_user("devhead")).json()
    assert len(queue) == 1 and queue[0]["employee"] == "ABC" and queue[0]["can_decide"] is True
    cid = queue[0]["id"]
    assert client.post(f"{API}/time/corrections/{cid}/decision", headers=as_user("abc"), json={"decision": "approve"}).status_code == 403
    assert client.post(f"{API}/time/corrections/{cid}/decision", headers=as_user("hrhead"), json={"decision": "approve"}).status_code == 404
    d = client.post(f"{API}/time/corrections/{cid}/decision", headers=as_user("devhead"), json={"decision": "approve", "note": "OK"}).json()
    assert d["status"] == "approved"
    tm = client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()
    assert tm["active_seconds"] == 2 * 3600 and tm["sessions"][0]["source"] == "manual"
    assert client.post(f"{API}/time/corrections/{cid}/decision", headers=as_user("devhead"), json={"decision": "approve"}).status_code == 409


def test_rejected_missing_time_adds_nothing(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    at(24 * 60)
    cid = missing(client, as_user, t["id"], 60, 120).json()["id"]
    r = client.post(f"{API}/time/corrections/{cid}/decision", headers=as_user("manager"), json={"decision": "reject", "note": "Not credible"})
    assert r.json()["status"] == "rejected" and r.json()["decision_note"] == "Not credible"
    assert client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()["active_seconds"] == 0


def test_missing_time_validation(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(120)
    ok(client, as_user, "abc", t["id"], "stop")  # 09:30-11:30 recorded
    at(24 * 60)
    assert missing(client, as_user, t["id"], 60, 90).json()["code"] == "TIME_OVERLAP"  # overlaps real time
    assert missing(client, as_user, t["id"], 300, 240).json()["code"] == "INVALID_TIME_RANGE"
    assert missing(client, as_user, t["id"], 24 * 60 + 60, 24 * 60 + 120).json()["code"] == "TIME_IN_FUTURE"
    assert missing(client, as_user, t["id"], 200, 200 + 17 * 60).json()["code"] == "TIME_RANGE_TOO_LONG"
    assert missing(client, as_user, t["id"], -20 * 24 * 60, -20 * 24 * 60 + 60).json()["code"] == "TIME_TOO_OLD"
    assert missing(client, as_user, t["id"], 300, 360, reason="x").status_code == 422
    assert missing(client, as_user, t["id"], 300, 360, who="owner").status_code == 403  # only the assignee requests it


def test_manager_adjusts_a_session_and_the_original_is_kept(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(120)
    ok(client, as_user, "abc", t["id"], "stop")
    log = client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()["sessions"][0]
    new = {"started_at": iso(0), "ended_at": iso(90), "reason": "Lunch break was not paused"}
    assert client.post(f"{API}/time/logs/{log['id']}/adjust", headers=as_user("abc"), json=new).status_code == 403
    r = client.post(f"{API}/time/logs/{log['id']}/adjust", headers=as_user("devhead"), json=new)
    assert r.status_code == 200 and r.json()["seconds"] == 90 * 60
    with seeded() as s:
        c = s.scalar(select(TimeCorrection).where(TimeCorrection.kind == "edit"))
        assert c.old_ended_at == BASE + timedelta(minutes=120) and c.new_ended_at == BASE + timedelta(minutes=90) and c.status == "approved"
    at(150)
    assert client.post(f"{API}/time/logs/{log['id']}/adjust", headers=as_user("hrhead"), json=new).status_code == 404  # out of scope


def test_adjust_refuses_overlap_and_running_sessions(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(60)
    ok(client, as_user, "abc", t["id"], "pause")
    at(120)
    ok(client, as_user, "abc", t["id"], "start")
    at(180)
    sessions = client.get(f"{API}/tasks/{t['id']}/time", headers=as_user("abc")).json()["sessions"]
    first, running = sessions
    r = client.post(f"{API}/time/logs/{running['id']}/adjust", headers=as_user("devhead"),
                    json={"started_at": iso(120), "ended_at": iso(170), "reason": "Trim the running one"})  # fmt: skip
    assert r.json()["code"] == "SESSION_RUNNING"
    r = client.post(f"{API}/time/logs/{first['id']}/adjust", headers=as_user("devhead"),
                    json={"started_at": iso(0), "ended_at": iso(150), "reason": "Stretch into the next session"})  # fmt: skip
    assert r.json()["code"] == "TIME_OVERLAP"


def test_time_logs_are_scoped_and_filterable(client, as_user, seeded):
    at(0)
    a = make(client, as_user, seeded, assignee=ABC)
    f = make(client, as_user, seeded, assignee=FE)
    ok(client, as_user, "abc", a["id"], "start")
    at(60)
    ok(client, as_user, "abc", a["id"], "stop")
    ok(client, as_user, "frontend", f["id"], "start")
    at(150)
    ok(client, as_user, "frontend", f["id"], "stop")
    names = lambda who, **q: {i["employee"]["full_name"] for i in client.get(f"{API}/time/logs", params=q, headers=as_user(who)).json()["items"]}  # noqa: E731
    assert names("abc") == {"ABC"} and names("frontend") == {"Frontend Dev"}  # employees see only their own
    assert names("devhead") == {"ABC", "Frontend Dev"} and names("owner") == {"ABC", "Frontend Dev"}
    assert names("hrhead") == set()  # another department
    assert names("owner", employee_id=a["assignee"]["id"]) == {"ABC"}
    total = client.get(f"{API}/time/logs", params={"task_id": f["id"]}, headers=as_user("owner")).json()["total_seconds"]
    assert total == 90 * 60
    assert client.get(f"{API}/time/logs", headers=as_user("admin")).status_code == 403


def test_workload_counts_what_is_left_not_the_full_estimate(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded, estimated_hours=12)
    ok(client, as_user, "abc", t["id"], "start")
    at(9 * 60)  # 9 hours worked (18:30 IST)
    ok(client, as_user, "abc", t["id"], "stop")
    row = next(r for r in client.get(f"{API}/workload", headers=as_user("owner")).json() if r["full_name"] == "ABC")
    assert row["open_estimated_hours"] == 12.0 and row["open_remaining_hours"] == 3.0 and row["next7_estimated_hours"] == 3.0
    mine = client.get(f"{API}/me/workload", headers=as_user("abc")).json()
    assert mine["full_name"] == "ABC" and mine["open_tasks"] == 1 and mine["is_me"] is True


def test_correction_list_shows_employees_only_their_own(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    at(24 * 60)
    missing(client, as_user, t["id"], 60, 120)
    assert len(client.get(f"{API}/time/corrections", headers=as_user("abc")).json()) == 1
    assert client.get(f"{API}/time/corrections", headers=as_user("frontend")).json() == []
    assert client.get(f"{API}/time/corrections", headers=as_user("hrhead")).json() == []
    assert len(client.get(f"{API}/time/corrections", headers=as_user("owner")).json()) == 1

