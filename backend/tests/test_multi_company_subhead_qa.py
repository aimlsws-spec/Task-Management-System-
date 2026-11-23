"""Tests for Multi-Company Architecture, Department SubHead, Multiple QA members, and Two-tier Project Review."""

from datetime import date, timedelta
from app.modules.org.models import Department, Employee
from tests.helpers import API, DEVHEAD, FE, ABC, SUPPORT, HRHEAD, eid, make, do, ok


FINISH_OK = {"summary": "Implemented and verified the chatbot API.", "tested": True, "no_time_reason": "Quick change, done in minutes"}


def test_multi_company_owner_creates_and_authorizes_ceo(client, as_user, seeded):
    # 1. Non-owner cannot create company
    r = client.post(f"{API}/companies", headers=as_user("ceo"), json={"name": "Alpha Corp", "code": "ALPHA"})
    assert r.status_code == 403

    # 2. Owner creates company
    r = client.post(f"{API}/companies", headers=as_user("owner"), json={"name": "Alpha Corp", "code": "ALPHA"})
    assert r.status_code == 201
    comp_id = r.json()["id"]
    assert r.json()["code"].upper() == "ALPHA"

    # 3. List companies: Owner sees all
    comps = client.get(f"{API}/companies", headers=as_user("owner")).json()
    assert any(c["id"] == comp_id for c in comps)

    # 4. CEO is not authorized yet for Alpha Corp
    r = client.post(f"{API}/departments", headers=as_user("ceo"), json={"name": "Alpha Eng", "code": "AENG", "company_id": comp_id})
    assert r.status_code == 403

    # 5. Owner authorizes CEO for Alpha Corp
    with seeded() as s:
        from app.modules.auth.models import User
        ceo_user = s.query(User).filter(User.email == "ceo@demo.example.com").first()
        assert ceo_user is not None
        ceo_uid = ceo_user.id

    r = client.post(f"{API}/companies/{comp_id}/ceos", headers=as_user("owner"), json={"user_id": ceo_uid})
    assert r.status_code == 201

    # 6. Now CEO can access Alpha Corp and create departments
    r = client.post(f"{API}/departments", headers=as_user("ceo"), json={"name": "Alpha Eng", "code": "AENG", "company_id": comp_id})
    assert r.status_code == 201
    dept_id = r.json()["id"]
    assert r.json()["company_id"] == comp_id

    # 7. Authorized CEO can send employee invite for Alpha Corp
    r = client.post(f"{API}/role-invites", headers=as_user("ceo"), json={"email": "alpha_dev@example.com", "role_code": "employee", "company_id": comp_id})
    assert r.status_code == 201
    assert r.json()["company_id"] == comp_id


def test_department_sub_head_and_rank_hierarchy(client, as_user, seeded):
    dev_id = eid(seeded, DEVHEAD)
    fe_id = eid(seeded, FE)

    with seeded() as s:
        d = s.query(Department).filter(Department.code == "DEV").first()
        dept_id = d.id

    # 1. Admin/Owner sets FE as SubHead of DEV
    r = client.put(f"{API}/departments/{dept_id}/subhead", headers=as_user("admin"), json={"sub_head_employee_id": fe_id})
    assert r.status_code == 200
    assert r.json()["sub_head_employee_id"] == fe_id

    # Verify FE has role 'sub_head' (rank 40)
    with seeded() as s:
        from app.modules.rbac.models import Role, UserRole
        fe_emp = s.get(Employee, fe_id)
        assert fe_emp is not None
        roles = s.query(Role.code).join(UserRole, UserRole.role_id == Role.id).filter(UserRole.user_id == fe_emp.user_id).all()
        role_codes = {rc[0] for rc in roles}
        assert "sub_head" in role_codes

    # 2. Head (rank 50) can assign task to SubHead (rank 40)
    t = make(client, as_user, seeded, who="devhead", assignee=FE, title="SubHead task from Head")
    assert t["id"] > 0
    assert t["assignee"]["id"] == fe_id

    # 3. SubHead (rank 40) cannot assign upward to Head (rank 50)
    r = client.post(f"{API}/tasks", headers=as_user("frontend"), json={
        "title": "Upward task", "description": "Attempting to assign up",
        "assignee_id": dev_id, "priority": "medium",
        "due_date": str(date.today() + timedelta(days=5)),
    })
    assert r.status_code == 403


def test_multiple_qa_members_shared_testing_status(client, as_user, seeded):
    fe_id = eid(seeded, FE)
    sup_id = eid(seeded, SUPPORT)
    abc_id = eid(seeded, ABC)

    # Create task with 2 QA members (fe and support)
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Multi-QA Feature", "description": "Testing multiple QAs",
        "assignee_id": abc_id, "priority": "high",
        "due_date": str(date.today() + timedelta(days=7)),
        "qa_employee_ids": [fe_id, sup_id],
    })
    assert r.status_code == 201
    t = r.json()["task"]
    qa_ids = {q["id"] for q in t["qa_members"]}
    assert qa_ids == {fe_id, sup_id}

    # Assignee completes work -> status is under_review at stage 'qa'
    ok(client, as_user, "abc", t["id"], "start")
    ok(client, as_user, "abc", t["id"], "complete", FINISH_OK)

    detail = client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()
    assert detail["status"] == "under_review"
    assert detail["review_stage"] == "qa"

    # Support (one of the assigned QAs) reviews and approves
    r = do(client, as_user, "support1", t["id"], "review", {"decision": "approve"})
    assert r.status_code == 200

    # Task progresses to 'head' or 'leadership'
    detail = client.get(f"{API}/tasks/{t['id']}", headers=as_user("owner")).json()
    assert detail["review_stage"] in ("head", "leadership")


def test_two_tier_project_review(client, as_user, seeded):
    dev_id = eid(seeded, DEVHEAD)

    # Create project with Head
    body = {
        "name": "Beta Platform", "description": "Beta project", "expected_result": "Working beta",
        "head_employee_id": dev_id,
        "points": [{"title": "Step 1"}],
        "ends_on": str(date.today() + timedelta(days=20)),
    }
    r = client.post(f"{API}/projects", headers=as_user("owner"), json=body)
    assert r.status_code == 201
    pid = r.json()["id"]

    # Assign and complete the task point
    p_detail = client.get(f"{API}/projects/{pid}", headers=as_user("owner")).json()
    point_id = p_detail["points"][0]["id"]

    assign_body = {"assignee_id": eid(seeded, ABC), "priority": "high", "due_date": str(date.today() + timedelta(days=5)), "estimated_hours": 4}
    r = client.post(f"{API}/projects/{pid}/points/{point_id}/assign", headers=as_user("owner"), json=assign_body)
    assert r.status_code == 201
    tid = r.json()["task"]["id"]

    ok(client, as_user, "abc", tid, "start")
    ok(client, as_user, "abc", tid, "complete", FINISH_OK)
    # devhead reviews task
    ok(client, as_user, "devhead", tid, "review", {"decision": "approve"})
    # leadership reviews task
    ok(client, as_user, "ceo", tid, "review", {"decision": "approve"})

    # Check project ready for review
    d = client.get(f"{API}/projects/{pid}", headers=as_user("owner")).json()
    assert d["ready_for_review"] is True
    assert d["status"] == "active"

    # Tier 1: Dev Head reviews and submits to Owner/CEO panel
    r = client.post(f"{API}/projects/{pid}/complete", headers=as_user("devhead"), json={"note": "Head verified everything"})
    assert r.status_code == 200
    proj_after_head = client.get(f"{API}/projects/{pid}", headers=as_user("owner")).json()
    # Project remains active until Owner/CEO completes it, but head_reviewed_at is recorded
    assert proj_after_head["status"] == "active"
    assert proj_after_head["head_reviewed_at"] is not None
    assert proj_after_head["head_review_note"] == "Head verified everything"

    # Tier 2: Owner marks project completed
    r = client.post(f"{API}/projects/{pid}/complete", headers=as_user("owner"), json={"note": "Executive sign-off"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_multiple_heads_task_and_fallback(client, as_user, seeded):
    dev_id = eid(seeded, DEVHEAD)
    fe_id = eid(seeded, FE)
    abc_id = eid(seeded, ABC)

    # 1. Admin/Owner sets FE as DEV department SubHead
    with seeded() as s:
        d = s.query(Department).filter(Department.code == "DEV").first()
        dept_id = d.id
    client.put(f"{API}/departments/{dept_id}/subhead", headers=as_user("admin"), json={"sub_head_employee_id": fe_id})

    # 2. Create task specifying multiple heads (DEVHEAD and FE)
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Multi-Head Feature", "description": "Testing multiple heads",
        "assignee_id": abc_id, "priority": "high",
        "due_date": str(date.today() + timedelta(days=7)),
        "head_employee_ids": [dev_id, fe_id],
    })
    assert r.status_code == 201
    t = r.json()["task"]
    head_ids = {h["id"] for h in t.get("heads", [])}
    assert head_ids == {dev_id, fe_id}

    # 3. Create task WITHOUT specifying heads -> auto fallback to employee's department Head & SubHead
    r2 = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Fallback Head Feature", "description": "Testing fallback heads",
        "assignee_id": abc_id, "priority": "medium",
        "due_date": str(date.today() + timedelta(days=5)),
    })
    assert r2.status_code == 201
    t2 = r2.json()["task"]
    head_ids_fallback = {h["id"] for h in t2.get("heads", [])}
    assert dev_id in head_ids_fallback
    assert fe_id in head_ids_fallback


def test_edit_and_delete_authority_strictly_owner_ceo(client, as_user, seeded):
    dev_id = eid(seeded, DEVHEAD)
    fe_id = eid(seeded, FE)
    abc_id = eid(seeded, ABC)

    # Create a task
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Protected Task", "description": "Only Owner/CEO can edit/cancel",
        "assignee_id": abc_id, "priority": "medium",
        "due_date": str(date.today() + timedelta(days=5)),
        "head_employee_ids": [dev_id, fe_id],
    })
    assert r.status_code == 201
    tid = r.json()["task"]["id"]

    # 1. Dev Head, SubHead (fe), and Assignee attempt to edit task -> all 403
    for user in ["devhead", "frontend", "abc"]:
        r_edit = client.patch(f"{API}/tasks/{tid}", headers=as_user(user), json={"title": "Hacked Title"})
        assert r_edit.status_code == 403, f"{user} was allowed to edit task"

    # Admin also cannot edit
    assert client.patch(f"{API}/tasks/{tid}", headers=as_user("admin"), json={"title": "Hacked Title"}).status_code in (403, 404)

    # 2. Owner can edit task -> 200
    r_owner = client.patch(f"{API}/tasks/{tid}", headers=as_user("owner"), json={"title": "Owner Renamed Task"})
    assert r_owner.status_code == 200

    # 3. CEO can edit task -> 200
    r_ceo = client.patch(f"{API}/tasks/{tid}", headers=as_user("ceo"), json={"title": "CEO Renamed Task"})
    assert r_ceo.status_code == 200

    # 4. Dev Head, SubHead attempt to cancel task -> 403
    for user in ["devhead", "frontend"]:
        r_cancel = client.post(f"{API}/tasks/{tid}/cancel", headers=as_user(user), json={"reason": "Cancel attempt"})
        assert r_cancel.status_code == 403, f"{user} was allowed to cancel task"

    # Admin also cannot cancel
    assert client.post(f"{API}/tasks/{tid}/cancel", headers=as_user("admin"), json={"reason": "Cancel attempt"}).status_code in (403, 404)

    # 5. Owner can cancel task -> 200
    r_cancel_owner = client.post(f"{API}/tasks/{tid}/cancel", headers=as_user("owner"), json={"reason": "Executive cancel"})
    assert r_cancel_owner.status_code == 200

    # 6. Projects: Create project
    r_p = client.post(f"{API}/projects", headers=as_user("owner"), json={
        "name": "Protected Project", "ends_on": str(date.today() + timedelta(days=10)),
        "points": [{"title": "Scope 1"}],
    })
    assert r_p.status_code == 201
    pid = r_p.json()["id"]
    point_id = r_p.json()["points"][0]["id"]

    # Dev Head, Admin attempt to edit project -> 403 or 404
    for user in ["devhead", "admin"]:
        assert client.patch(f"{API}/projects/{pid}", headers=as_user(user), json={"name": "Hacked"}).status_code in (403, 404)
        assert client.delete(f"{API}/projects/{pid}/points/{point_id}", headers=as_user(user)).status_code in (403, 404)
        assert client.delete(f"{API}/projects/{pid}", headers=as_user(user)).status_code in (403, 404)

    # CEO can edit project -> 200
    assert client.patch(f"{API}/projects/{pid}", headers=as_user("ceo"), json={"name": "CEO Renamed"}).status_code == 200

    # Owner can delete point and delete project
    assert client.delete(f"{API}/projects/{pid}/points/{point_id}", headers=as_user("owner")).status_code == 204
    assert client.delete(f"{API}/projects/{pid}", headers=as_user("owner")).status_code == 204


def test_task_transfer_and_history(client, as_user, seeded):
    fe_id = eid(seeded, FE)
    abc_id = eid(seeded, ABC)

    # 1. Owner creates task assigned to abc
    r = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Transferrable Task", "description": "Track audit trail",
        "assignee_id": abc_id, "priority": "medium",
        "due_date": str(date.today() + timedelta(days=5)),
    })
    assert r.status_code == 201
    tid = r.json()["task"]["id"]

    # 2. Devhead transfers task to FE
    r_reassign1 = client.post(f"{API}/tasks/{tid}/reassign", headers=as_user("devhead"), json={
        "assignee_id": fe_id, "reason": "Handing off to FE specialist",
    })
    assert r_reassign1.status_code == 200

    # 3. CEO transfers task back to ABC
    r_reassign2 = client.post(f"{API}/tasks/{tid}/reassign", headers=as_user("ceo"), json={
        "assignee_id": abc_id, "reason": "CEO transfer back to ABC",
    })
    assert r_reassign2.status_code == 200

    # 4. Check TaskDetail includes assignment_history
    detail = client.get(f"{API}/tasks/{tid}", headers=as_user("owner")).json()
    history = detail.get("assignment_history", [])
    assert len(history) >= 2  # initial + transfers
    # Check that latest assignee is ABC
    assert detail["assignee"]["id"] == abc_id
    # Check reasons in history
    reasons = [h.get("reason") for h in history if h.get("reason")]
    assert "Handing off to FE specialist" in reasons
    assert "CEO transfer back to ABC" in reasons


def test_cross_department_peer_head_assignment(client, as_user, seeded):
    hr_id = eid(seeded, HRHEAD)

    # Devhead assigns task to HRHEAD (peer department head in same company)
    r = client.post(f"{API}/tasks", headers=as_user("devhead"), json={
        "title": "Cross Department Task", "description": "From Dev Head to HR Head",
        "assignee_id": hr_id, "priority": "medium",
        "due_date": str(date.today() + timedelta(days=3)),
    })
    assert r.status_code == 201
    t = r.json()["task"]
    assert t["assignee"]["id"] == hr_id


def test_multi_heads_and_head_also_acting_as_subhead(client, as_user, seeded):
    dev_id = eid(seeded, DEVHEAD)
    fe_id = eid(seeded, FE)
    hr_id = eid(seeded, HRHEAD)

    with seeded() as s:
        d = s.query(Department).filter(Department.code == "DEV").first()
        dept_id = d.id

    # Admin sets multiple heads (DEVHEAD, HRHEAD) and subheads (DEVHEAD, FE)
    # Notice DEVHEAD is both Head and SubHead!
    r = client.put(
        f"{API}/departments/{dept_id}/leaders",
        headers=as_user("admin"),
        json={"head_employee_ids": [dev_id, hr_id], "sub_head_employee_ids": [dev_id, fe_id]},
    )
    assert r.status_code == 200
    data = r.json()
    assert dev_id in data["head_employee_ids"]
    assert hr_id in data["head_employee_ids"]
    assert dev_id in data["sub_head_employee_ids"]
    assert fe_id in data["sub_head_employee_ids"]


def test_project_task_inherits_deadline_and_special_note(client, as_user, seeded):
    abc_id = eid(seeded, ABC)
    fe_id = eid(seeded, FE)

    # 1. Create project with priority and special_note
    p_ends = str(date.today() + timedelta(days=14))
    r = client.post(f"{API}/projects", headers=as_user("owner"), json={
        "name": "Chatbot 2.0",
        "priority": "critical",
        "special_note": "Confidential AI project",
        "ends_on": p_ends,
        "points": [{"title": "API Backend", "expected_result": "Working REST API"}],
    })
    assert r.status_code == 201
    pr_id = r.json()["id"]

    # Verify project summary contains priority and special_note
    pr_get = client.get(f"{API}/projects/{pr_id}", headers=as_user("owner")).json()
    assert pr_get["priority"] == "critical"
    assert pr_get["special_note"] == "Confidential AI project"

    # 2. Assign point without separate due_date
    point_id = pr_get["points"][0]["id"]
    r_assign = client.post(f"{API}/projects/{pr_id}/points/{point_id}/assign", headers=as_user("owner"), json={
        "assignee_id": abc_id,
        "priority": "high",
        "special_note": "Deliver with OpenAPI docs",
    })
    assert r_assign.status_code == 201
    task_id = r_assign.json()["task"]["id"]

    # Verify task inherited project deadline
    t_get = client.get(f"{API}/tasks/{task_id}", headers=as_user("owner")).json()
    assert t_get["due_at"].startswith(p_ends)
    assert t_get["special_note"] == "Deliver with OpenAPI docs"

    # 3. Create task directly linked to project without due_date
    r_task = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Direct Project Task",
        "description": "Task created under project without due_date",
        "project_id": pr_id,
        "assignee_id": fe_id,
        "priority": "low",
        "special_note": "Follow project styling guidelines",
    })
    assert r_task.status_code == 201
    direct_t = r_task.json()["task"]
    assert direct_t["due_at"].startswith(p_ends)

    # Cleanup project
    client.delete(f"{API}/projects/{pr_id}", headers=as_user("owner"))


def test_ceo_hierarchy_scope_restrictions(client, as_user, seeded):
    fe_id = eid(seeded, FE)
    abc_id = eid(seeded, ABC)

    # 1. Create a separate company without granting access to CEO
    r_comp = client.post(f"{API}/companies", headers=as_user("owner"), json={"name": "Beta Industries", "code": "BETA"})
    assert r_comp.status_code == 201
    beta_id = r_comp.json()["id"]

    # Create employee in Beta company
    r_emp = client.post(f"{API}/employees", headers=as_user("admin"), json={
        "email": "beta_worker@example.com",
        "full_name": "Beta Worker",
        "department_id": 1,
        "temp_password": "Password123!",
    })
    assert r_emp.status_code == 201
    beta_emp_id = r_emp.json()["id"]

    # Assign beta_worker to Beta company
    client.put(f"{API}/employees/{beta_emp_id}/companies", headers=as_user("admin"), json={"company_ids": [beta_id]})

    # CEO attempts to change manager of Beta Worker -> 403 Forbidden
    r_mgr = client.post(f"{API}/hierarchy/relationships", headers=as_user("ceo"), json={
        "employee_id": beta_emp_id,
        "reports_to_id": fe_id,
    })
    assert r_mgr.status_code == 403

    # But CEO CAN manage hierarchy for employees in Company 1 (authorized default company)
    r_mgr_ok = client.post(f"{API}/hierarchy/relationships", headers=as_user("ceo"), json={
        "employee_id": abc_id,
        "reports_to_id": fe_id,
    })
    assert r_mgr_ok.status_code == 204


def test_owner_creates_company_and_appoints_ceo_with_invitation(client, as_user, seeded):
    # 1. Owner creates company and appoints CEO with invitation email
    r = client.post(f"{API}/companies", headers=as_user("owner"), json={
        "name": "Nova Tech",
        "code": "NOVA",
        "ceo_email": "appointed_ceo@novatech.com",
    })
    assert r.status_code == 201
    comp_id = r.json()["id"]

    # Verify CEO invite was generated with activation link queued
    with seeded() as s:
        from app.modules.org.models import RoleInvite
        from app.modules.notifications.models import EmailLog
        inv = s.query(RoleInvite).filter(RoleInvite.email == "appointed_ceo@novatech.com").first()
        assert inv is not None
        assert inv.company_id == comp_id

        # Verify invitation email log
        email = s.query(EmailLog).filter(EmailLog.to_email == "appointed_ceo@novatech.com").first()
        assert email is not None
        assert "CEO" in email.subject
        assert "/signup" in email.body_text

    # 2. Owner can also invite CEO via assign_company_ceo endpoint for an un-registered email
    r_assign = client.post(f"{API}/companies/{comp_id}/ceos", headers=as_user("owner"), json={
        "email": "second_ceo@novatech.com"
    })
    assert r_assign.status_code == 201
    with seeded() as s:
        from app.modules.org.models import RoleInvite
        inv2 = s.query(RoleInvite).filter(RoleInvite.email == "second_ceo@novatech.com").first()
        assert inv2 is not None
        assert inv2.company_id == comp_id


def test_ceo_completes_task_and_submits_to_owner(client, as_user, seeded):
    fe_id = eid(seeded, FE)

    # 1. Owner creates task assigned to FE
    r_task = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Build Integration Service",
        "description": "Critical backend integration service",
        "assignee_id": fe_id,
        "due_date": (date.today() + timedelta(days=5)).isoformat(),
        "priority": "high",
    })
    assert r_task.status_code == 201
    task_id = r_task.json()["task"]["id"]

    # 2. Check CEO allowed actions includes submit_to_owner
    t_ceo_view = client.get(f"{API}/tasks/{task_id}", headers=as_user("ceo")).json()
    assert "submit_to_owner" in t_ceo_view["allowed_actions"]

    # 3. CEO completes the task and submits directly to Owner
    r_sub = client.post(f"{API}/tasks/{task_id}/submit-to-owner", headers=as_user("ceo"), json={
        "summary": "Completed service integration directly; verified all endpoints.",
        "tested": True,
    })
    assert r_sub.status_code == 200
    t_after = r_sub.json()
    assert t_after["status"] == "under_review"
    assert t_after["review_stage"] == "leadership"
    assert t_after["progress_pct"] == 100

    # 4. Owner reviews and approves task
    r_rev = client.post(f"{API}/tasks/{task_id}/review", headers=as_user("owner"), json={
        "decision": "approve",
        "comment": "Approved by Owner. Looks solid.",
    })
    assert r_rev.status_code == 200
    t_done = r_rev.json()
    assert t_done["status"] == "completed"
    assert t_done["verified_at"] is not None


def test_admin_management_scope_and_task_restrictions(client, as_user, seeded):
    fe_id = eid(seeded, FE)

    # 1. Admin can access system management resources across all companies
    comps = client.get(f"{API}/companies", headers=as_user("admin"))
    assert comps.status_code == 200
    depts = client.get(f"{API}/departments", headers=as_user("admin"))
    assert depts.status_code == 200
    emps = client.get(f"{API}/employees", headers=as_user("admin"))
    assert emps.status_code == 200

    # 2. Admin CANNOT create tasks or projects
    r_task_create = client.post(f"{API}/tasks", headers=as_user("admin"), json={
        "title": "Admin Unauthorized Task",
        "description": "Should fail",
        "assignee_id": fe_id,
        "due_date": (date.today() + timedelta(days=2)).isoformat(),
    })
    assert r_task_create.status_code == 403

    r_proj_create = client.post(f"{API}/projects", headers=as_user("admin"), json={
        "name": "Admin Unauthorized Project",
        "ends_on": (date.today() + timedelta(days=10)).isoformat(),
    })
    assert r_proj_create.status_code == 403

    # 3. Create a task via Owner, verify Admin cannot edit or cancel it
    r_task = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Owner Created Task",
        "description": "Testing admin lack of task edit/cancel permissions",
        "assignee_id": fe_id,
        "due_date": (date.today() + timedelta(days=3)).isoformat(),
    })
    assert r_task.status_code == 201
    tid = r_task.json()["task"]["id"]

    # Admin cannot edit
    r_edit = client.patch(f"{API}/tasks/{tid}", headers=as_user("admin"), json={"title": "Admin Modified Title"})
    assert r_edit.status_code == 403

    # Admin cannot cancel
    r_cancel = client.post(f"{API}/tasks/{tid}/cancel", headers=as_user("admin"), json={"reason": "Admin cancel attempt"})
    assert r_cancel.status_code == 403

    # Clean up
    client.post(f"{API}/tasks/{tid}/cancel", headers=as_user("owner"), json={"reason": "Cleanup"})


def test_project_with_multiple_tasks_and_multiple_employees(client, as_user, seeded):
    fe_id = eid(seeded, FE)
    abc_id = eid(seeded, ABC)

    # 1. Create project with multiple employees
    r_proj = client.post(f"{API}/projects", headers=as_user("owner"), json={
        "name": "Multi-Task Project",
        "description": "A project with multiple tasks and employees",
        "member_ids": [fe_id, abc_id],
        "ends_on": (date.today() + timedelta(days=14)).isoformat(),
    })
    assert r_proj.status_code == 201
    pr_id = r_proj.json()["id"]

    # 2. Add multiple tasks to the project
    t1 = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Task 1: Architecture",
        "description": "First task in project",
        "project_id": pr_id,
        "assignee_id": fe_id,
    })
    assert t1.status_code == 201

    t2 = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Task 2: Implementation",
        "description": "Second task in project",
        "project_id": pr_id,
        "assignee_id": abc_id,
    })
    assert t2.status_code == 201

    # 3. Retrieve project and verify tasks & multiple members
    pr_detail = client.get(f"{API}/projects/{pr_id}", headers=as_user("owner")).json()
    assert len(pr_detail["members"]) == 2
    member_ids = [m["id"] for m in pr_detail["members"]]
    assert fe_id in member_ids and abc_id in member_ids
    assert len(pr_detail["tasks"]) == 2

    # Clean up
    client.delete(f"{API}/projects/{pr_id}", headers=as_user("owner"))


def test_owner_and_ceo_create_departments_later(client, as_user, seeded):
    # 1. Owner creates company
    r_comp = client.post(f"{API}/companies", headers=as_user("owner"), json={"name": "Delta Holdings", "code": "DELTA"})
    assert r_comp.status_code == 201
    delta_id = r_comp.json()["id"]

    # 2. Owner authorizes CEO for company Delta
    with seeded() as s:
        from app.modules.auth.models import User
        ceo_user = s.query(User).filter(User.email == "ceo@demo.example.com").first()
        ceo_uid = ceo_user.id
    client.post(f"{API}/companies/{delta_id}/ceos", headers=as_user("owner"), json={"user_id": ceo_uid})

    # 3. Owner creates an additional department for Delta later
    r_d1 = client.post(f"{API}/departments", headers=as_user("owner"), json={
        "name": "Delta Marketing",
        "code": "D_MKT",
        "company_id": delta_id,
    })
    assert r_d1.status_code == 201
    assert r_d1.json()["company_id"] == delta_id

    # 4. CEO creates another additional department for Delta later
    r_d2 = client.post(f"{API}/departments", headers=as_user("ceo"), json={
        "name": "Delta Product",
        "code": "D_PROD",
        "company_id": delta_id,
    })
    assert r_d2.status_code == 201
    assert r_d2.json()["company_id"] == delta_id

    # 5. List departments filtered by company_id
    depts = client.get(f"{API}/departments?company_id={delta_id}", headers=as_user("ceo")).json()
    dept_codes = [d["code"] for d in depts]
    assert "D_MKT" in dept_codes
    assert "D_PROD" in dept_codes


def test_login_persistence_and_refresh_token(client, monkeypatch, seeded):
    from tests.conftest import PASSWORD
    from tests.test_auth import _enable_multi
    # 1. In default cookie mode: login sets httpOnly cookie with max_age
    r = client.post(f"{API}/auth/login", json={"email": "owner@demo.example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert client.cookies.get("tms_refresh")

    # Refresh via cookie
    r_ref = client.post(f"{API}/auth/refresh", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r_ref.status_code == 200
    assert "access_token" in r_ref.json()

    # 2. In multi-session dev mode: login returns refresh_token in JSON body
    _enable_multi(monkeypatch)
    r2 = client.post(f"{API}/auth/login", json={"email": "owner@demo.example.com", "password": PASSWORD})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "refresh_token" in data2
    rt = data2["refresh_token"]

    # Refresh via JSON body
    r2_ref = client.post(
        f"{API}/auth/refresh",
        headers={"X-Requested-With": "XMLHttpRequest"},
        json={"refresh_token": rt},
    )
    assert r2_ref.status_code == 200
    assert "access_token" in r2_ref.json()
    assert "refresh_token" in r2_ref.json()


def test_company_specific_work_isolation(client, as_user, seeded):
    # 1. Owner creates Company Gamma
    r_comp = client.post(f"{API}/companies", headers=as_user("owner"), json={"name": "Gamma Corp", "code": "GAMMA"})
    assert r_comp.status_code == 201
    gamma_id = r_comp.json()["id"]

    # 2. Create department and employee belonging exclusively to Gamma Corp
    r_dept = client.post(f"{API}/departments", headers=as_user("owner"), json={"name": "Gamma Tech", "code": "GTECH", "company_id": gamma_id})
    assert r_dept.status_code == 201
    gdept_id = r_dept.json()["id"]

    from tests.conftest import PASSWORD
    r_emp = client.post(f"{API}/employees", headers=as_user("owner"), json={
        "email": "gamma_dev@example.com",
        "full_name": "Gamma Developer",
        "department_id": gdept_id,
        "company_id": gamma_id,
        "job_title": "Developer",
        "temp_password": PASSWORD,
        "role_codes": ["employee"],
    })
    assert r_emp.status_code == 201
    gamma_emp_id = r_emp.json()["id"]
    assert r_emp.json()["company_id"] == gamma_id

    fe_id = eid(seeded, FE)  # belonging to default company 1

    # 3. Trying to create a task in default company (company_id=1) assigned to Gamma employee is rejected
    r_t_fail = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Cross company task",
        "description": "Should fail",
        "company_id": 1,
        "due_date": str(date.today() + timedelta(days=5)),
        "assignee_id": gamma_emp_id,
    })
    assert r_t_fail.status_code == 403
    assert "does not belong" in r_t_fail.json()["message"]

    # 4. Trying to create a project in default company with Gamma employee in members is rejected
    r_p_fail = client.post(f"{API}/projects", headers=as_user("owner"), json={
        "name": "Default Project",
        "company_id": 1,
        "ends_on": str(date.today() + timedelta(days=10)),
        "member_ids": [gamma_emp_id],
    })
    assert r_p_fail.status_code == 403
    assert "does not belong" in r_p_fail.json()["message"]

    # 5. Creating a project in Gamma Corp with Gamma employee succeeds
    r_p_ok = client.post(f"{API}/projects", headers=as_user("owner"), json={
        "name": "Gamma Cloud Platform",
        "company_id": gamma_id,
        "ends_on": str(date.today() + timedelta(days=14)),
        "assignee_id": gamma_emp_id,
        "member_ids": [gamma_emp_id],
    })
    assert r_p_ok.status_code == 201
    gamma_pr_id = r_p_ok.json()["id"]
    assert r_p_ok.json()["company"]["id"] == gamma_id
    assert r_p_ok.json()["company"]["code"] == "gamma"

    # 6. Task created inside Gamma project automatically inherits Gamma company
    r_t_ok = client.post(f"{API}/tasks", headers=as_user("owner"), json={
        "title": "Setup Gamma Infrastructure",
        "description": "Project task inheriting company",
        "project_id": gamma_pr_id,
        "assignee_id": gamma_emp_id,
    })
    assert r_t_ok.status_code == 201
    task_data = r_t_ok.json()["task"]
    assert task_data["company_id"] == gamma_id
    assert task_data["company"]["id"] == gamma_id
    assert task_data["company"]["code"] == "gamma"
    gamma_task_id = task_data["id"]

    # 7. Reassigning Gamma task to an employee of another company is rejected
    r_reassign_fail = client.post(
        f"{API}/tasks/{gamma_task_id}/reassign",
        headers=as_user("owner"),
        json={"assignee_id": fe_id, "reason": "Attempting cross-company transfer"},
    )
    assert r_reassign_fail.status_code == 403
    assert "does not belong" in r_reassign_fail.json()["message"]

    # 8. Workload query filtered by company_id
    gamma_workload = client.get(f"{API}/workload?company_id={gamma_id}", headers=as_user("owner")).json()
    emp_ids_in_gamma = [w["employee_id"] for w in gamma_workload]
    assert gamma_emp_id in emp_ids_in_gamma
    assert fe_id not in emp_ids_in_gamma

    # 9. Clean up
    client.delete(f"{API}/projects/{gamma_pr_id}", headers=as_user("owner"))


