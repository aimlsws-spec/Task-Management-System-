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

