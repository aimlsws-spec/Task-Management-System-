"""Matrix-driven authorization tests (doc 03). One test per (endpoint x role) cell.

Denied roles must get 403; allowed roles must get anything EXCEPT 401/403 (we send ids/payloads that cannot
succeed, so allowed callers get 404/422 and nothing is ever mutated). Unauthenticated callers get 401.
Changing who may call an endpoint means changing this table (and doc 03) - reviewed by a human.

Organization setup (employees, departments, hierarchy, roles, settings) is ADMIN-only by decision."""

import pytest

API = "/api/v1"
# one demo user per role
ALL = {"admin", "owner", "ceo", "manager", "devhead", "abc"}
ADMIN = {"admin", "owner"}  # Owner has full system access and all Admin capabilities
ADMIN_OR_CEO = {"admin", "owner", "ceo"}  # CEO can manage employees, depts, hierarchy, invites in their company
AUDIT = {"admin", "owner"}  # Owner can view audit log
WORK = {"owner", "ceo", "manager", "devhead", "abc"}  # task.view: everyone except the Admin
ASSIGNERS = {"owner", "ceo", "manager", "devhead"}  # task.create + task.assign (employees and Admin cannot)

# (method, path, json body, roles allowed)
MATRIX = [
    ("GET", "/auth/me", None, ALL),
    ("GET", "/employees", None, ALL),  # scope-filtered, not permission-gated
    ("GET", "/employees/999999", None, ALL),  # allowed roles see 404 (also what out-of-scope looks like)
    ("POST", "/employees", {"bad": 1}, ADMIN_OR_CEO),
    ("PATCH", "/employees/999999", {"phone": "1"}, ADMIN_OR_CEO),
    ("POST", "/employees/999999/deactivate", None, ADMIN_OR_CEO),
    ("POST", "/employees/999999/reactivate", None, ADMIN_OR_CEO),
    ("GET", "/departments", None, ALL),
    ("POST", "/departments", {"bad": 1}, ADMIN_OR_CEO),
    ("PATCH", "/departments/999999", {"is_active": True}, ADMIN_OR_CEO),
    ("DELETE", "/departments/999999", None, ADMIN_OR_CEO),
    ("PUT", "/departments/999999/head", {"head_employee_id": None}, ADMIN_OR_CEO),
    ("GET", "/hierarchy/tree", None, ALL),
    ("POST", "/hierarchy/relationships", {"employee_id": 999999, "reports_to_id": None}, ADMIN_OR_CEO),
    ("GET", "/role-invites", None, ADMIN_OR_CEO),
    ("POST", "/role-invites", {"bad": 1}, ADMIN_OR_CEO),
    ("DELETE", "/role-invites/999999", None, ADMIN_OR_CEO),
    ("POST", "/role-invites/999999/resend", None, ADMIN_OR_CEO),
    ("GET", "/roles", None, ADMIN),
    ("GET", "/permissions", None, ADMIN),
    ("PUT", "/roles/999999/permissions", {"grants": []}, ADMIN),
    ("PUT", "/users/999999/roles", {"role_codes": ["employee"]}, ADMIN),
    ("GET", "/admin/settings", None, ADMIN),
    ("PUT", "/admin/settings", {"eod_time": "18:30"}, ADMIN),
    ("POST", "/holidays", {"bad": 1}, ADMIN),
    ("DELETE", "/holidays/999999", None, ADMIN),
    ("GET", "/admin/audit-logs", None, AUDIT),
    # --- Phase 3: tasks, workload, projects ---
    ("GET", "/tasks", None, WORK),
    ("POST", "/tasks", {"bad": 1}, ASSIGNERS),
    ("GET", "/tasks/999999", None, WORK),
    ("PATCH", "/tasks/999999", {"title": "abc"}, WORK),
    ("POST", "/tasks/999999/reassign", {"assignee_id": 1}, WORK),
    ("POST", "/tasks/999999/priority", {"priority": "low"}, WORK),
    ("POST", "/tasks/999999/cancel", {"reason": "abcdef"}, WORK),
    ("POST", "/tasks/999999/acknowledge", None, WORK),
    ("GET", "/tasks/999999/timeline", None, WORK),
    ("GET", "/attachments/999999/download", None, WORK),
    ("GET", "/workload", None, ASSIGNERS),
    ("GET", "/projects", None, ALL),
    ("POST", "/projects", {"bad": 1}, ASSIGNERS),
    ("PATCH", "/projects/999999", {"name": "abc"}, ASSIGNERS),
    ("GET", "/task-meta", None, ALL),
    # --- projects (ADR 003): create/edit by project.manage; only Owner and CEO sign a project off
    ("GET", "/projects/999999", None, ALL),
    ("PATCH", "/projects/999999", {"name": "abc"}, ASSIGNERS),
    ("POST", "/projects/999999/points", {"title": "abc"}, ASSIGNERS),
    ("PATCH", "/projects/999999/points/1", {"title": "abc"}, ASSIGNERS),
    ("DELETE", "/projects/999999/points/1", None, ASSIGNERS),
    ("POST", "/projects/999999/points/1/assign", {"assignee_id": 1, "priority": "low", "due_date": "2030-01-01", "estimated_hours": 1}, ASSIGNERS),
    ("POST", "/projects/999999/complete", {}, {"owner", "ceo", "devhead", "manager"}),
    # --- Phase 4: the employee's work, finishing, review, time ---
    ("POST", "/tasks/999999/start", None, WORK),
    ("POST", "/tasks/999999/pause", None, WORK),
    ("POST", "/tasks/999999/stop", None, WORK),
    ("POST", "/tasks/999999/hold", {"reason": "abc"}, WORK),
    ("POST", "/tasks/999999/unhold", None, WORK),
    ("POST", "/tasks/999999/progress", {"progress_pct": 1, "note": "abc"}, WORK),
    ("POST", "/tasks/999999/complete", {"summary": "abcdef", "tested": True}, WORK),
    ("POST", "/tasks/999999/submit-for-review", {"summary": "abcdef", "tested": True}, WORK),
    ("POST", "/tasks/999999/review", {"decision": "approve"}, WORK),
    ("POST", "/tasks/999999/verify", None, WORK),
    ("POST", "/tasks/999999/revert", {"reason_code": "other", "reason": "abcdef"}, WORK),
    ("GET", "/tasks/999999/time", None, WORK),
    ("GET", "/time/active", None, WORK),
    ("POST", "/time/heartbeat", None, WORK),
    ("POST", "/time/checkin/continue", None, WORK),
    ("GET", "/time/unconfirmed", None, WORK),
    ("GET", "/time/logs", None, WORK),
    ("POST", "/time/logs/999999/confirm", None, WORK),
    ("POST", "/time/logs/999999/adjust", {"bad": 1}, ASSIGNERS),
    ("POST", "/time/corrections", {"bad": 1}, WORK),
    ("GET", "/time/corrections", None, WORK),
    ("POST", "/time/corrections/999999/decision", {"decision": "approve"}, ASSIGNERS),
    ("GET", "/me/workload", None, WORK),
    ("POST", "/admin/jobs/timer-guard", None, ADMIN),
    # --- Phase 5: deadlines, extension requests, delay explanations ---
    ("POST", "/tasks/999999/deadline", {"due_date": "2030-01-01", "reason": "abcdefghij"}, WORK),
    ("GET", "/tasks/999999/deadline-history", None, WORK),
    ("POST", "/tasks/999999/extension-requests", {"due_date": "2030-01-01", "reason": "abcdefghij"}, WORK),
    ("GET", "/extension-requests", None, ASSIGNERS),
    ("POST", "/extension-requests/999999/decision", {"decision": "approve"}, ASSIGNERS),
    ("GET", "/stats/deadlines", None, WORK),
    ("POST", "/tasks/999999/delay-reasons", {"reason": "abcdef", "progress_pct": 1, "work_completed": "abcdef", "remaining_work": "abc", "expected_date": "2030-01-01"}, WORK),
    ("GET", "/tasks/999999/delay-reasons", None, WORK),
    ("POST", "/delay-reasons/999999/review", {"decision": "accepted"}, ASSIGNERS),
    ("GET", "/delays/queue", None, ASSIGNERS),
    # --- Phase 8 + head workflow: dashboards, reports, exports, ownership ---
    ("GET", "/dashboard", None, WORK),
    ("GET", "/reports", None, WORK),
    ("GET", "/reports/completion", None, WORK),
    ("GET", "/reports/overdue", None, WORK),
    ("GET", "/reports/time/export?format=csv", None, WORK),
    ("GET", "/reports/nope", None, WORK),
    ("POST", "/tasks/999999/take-ownership", {}, WORK),
    # --- Phase 6: notifications (everyone's own), real-time ticket, Admin controls ---
    ("GET", "/notifications", None, ALL),
    ("GET", "/notifications/unread-count", None, ALL),
    ("PUT", "/notifications/999999/read", None, ALL),
    ("POST", "/notifications/read-all", None, ALL),
    ("GET", "/me/notification-preferences", None, ALL),
    ("PUT", "/me/notification-preferences", {"event_type": "TASK_CREATED", "channel": "email", "enabled": True}, ALL),
    ("GET", "/admin/notification-rules", None, ADMIN),
    ("PATCH", "/admin/notification-rules/999999", {"enabled": True}, ADMIN),
    ("GET", "/admin/reminder-rules", None, ADMIN),
    ("PATCH", "/admin/reminder-rules/999999", {"enabled": True}, ADMIN),
    ("GET", "/admin/email-logs", None, ADMIN),
    ("POST", "/admin/email-logs/999999/retry", None, ADMIN),
    ("GET", "/admin/jobs/failures", None, ADMIN),
    ("GET", "/admin/jobs/status", None, ADMIN),
    ("POST", "/admin/jobs/run-now", None, ADMIN),
    # --- Phase 7: blockers, comments, questions ---
    ("POST", "/tasks/999999/blockers", {"bad": 1}, WORK),
    ("GET", "/tasks/999999/blockers", None, WORK),
    ("GET", "/blockers", None, WORK),
    ("GET", "/blockers/999999", None, WORK),
    ("POST", "/blockers/999999/acknowledge", None, WORK),
    ("POST", "/blockers/999999/assign", {"owner_employee_id": 1}, WORK),
    ("POST", "/blockers/999999/start", None, WORK),
    ("POST", "/blockers/999999/reply", {"note": "abc"}, WORK),
    ("POST", "/blockers/999999/resolve", {"note": "abc"}, WORK),
    ("POST", "/blockers/999999/close", None, WORK),
    ("POST", "/blockers/999999/reopen", {"note": "abc"}, WORK),
    ("POST", "/blockers/999999/escalate", {"note": "abc"}, WORK),
    ("GET", "/tasks/999999/comments", None, WORK),
    ("GET", "/tasks/999999/mentionable", None, WORK),
    ("POST", "/tasks/999999/comments", {"kind": "comment", "body": "abc"}, WORK),
    ("PATCH", "/comments/999999", {"body": "abc"}, WORK),
    ("GET", "/holidays", None, ALL),
    ("GET", "/work-calendar?from_=2026-11-01&to=2026-11-02", None, ALL),
]
CASES = [(m, p, b, role, role in allowed) for m, p, b, allowed in MATRIX for role in sorted(ALL)]


@pytest.mark.parametrize("method,path,body,role,allowed", CASES, ids=[f"{m} {p} as {r}" for m, p, b, r, a in CASES])
def test_matrix_cell(client, as_user, method, path, body, role, allowed):
    r = client.request(method, API + path, headers=as_user(role), json=body)
    if allowed:
        assert r.status_code not in (401, 403), f"{role} should be allowed on {method} {path}, got {r.status_code} {r.text}"
    else:
        assert r.status_code == 403, f"{role} must be denied on {method} {path}, got {r.status_code}"


@pytest.mark.parametrize("method,path,body", [(m, p, b) for m, p, b, _ in MATRIX if p not in ("/holidays",) and "work-calendar" not in p])
def test_unauthenticated_is_401(client, method, path, body):
    assert client.request(method, API + path, json=body).status_code == 401


# ---------- seeded role definitions (invariants from doc 03) ----------

ORG_SETUP = {"employee.manage", "department.manage", "hierarchy.manage", "role.manage", "settings.manage", "notification.rules.manage"}


def perms(client, as_user, who):
    return client.get(f"{API}/auth/me", headers=as_user(who)).json()["permissions"]


def test_seeded_scopes_match_doc03(client, as_user):
    assert set(perms(client, as_user, "owner").values()) == {"organization"}
    assert set(perms(client, as_user, "ceo").values()) == {"organization"}
    assert set(perms(client, as_user, "manager").values()) == {"team"}
    assert set(perms(client, as_user, "devhead").values()) == {"department"}
    assert set(perms(client, as_user, "abc").values()) == {"self"}


def test_admin_holds_all_org_setup_and_no_task_authority(client, as_user):
    p = perms(client, as_user, "admin")
    assert ORG_SETUP <= set(p)
    assert not {c for c in p if c.startswith(("task.", "time.", "delay.", "blocker.", "report."))}  # setup only


def test_org_setup_is_held_by_admin_and_owner(client, as_user):
    assert ORG_SETUP <= set(perms(client, as_user, "admin"))
    assert ORG_SETUP <= set(perms(client, as_user, "owner"))
    admin_only = {"role.manage", "settings.manage", "notification.rules.manage"}
    for who in ("ceo", "manager", "devhead", "abc"):
        assert not admin_only & set(perms(client, as_user, who)), who


def test_owner_and_ceo_keep_full_work_authority(client, as_user):
    for who in ("owner", "ceo"):
        p = perms(client, as_user, who)
        assert {"task.create", "task.assign", "task.deadline.edit", "task.verify", "delay.review"} <= set(p)
    assert "audit.view" in perms(client, as_user, "owner")
    assert "audit.view" not in perms(client, as_user, "ceo")


def test_employees_have_no_management_permissions(client, as_user):
    emp = perms(client, as_user, "abc")
    for p in ("task.create", "task.assign", "task.deadline.edit", "task.priority.change", "task.verify", "employee.manage",
              "department.manage", "role.manage", "settings.manage", "audit.view", "delay.review", "blocker.manage"):  # fmt: skip
        assert p not in emp


def test_employee_can_raise_blockers_but_not_manage_them(client, as_user):
    emp = perms(client, as_user, "abc")
    assert "blocker.raise" in emp and "blocker.manage" not in emp
