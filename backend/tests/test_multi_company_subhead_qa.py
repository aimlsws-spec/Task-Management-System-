"""Tests for Multi-Company Architecture, Department SubHead, Multiple QA members, and Two-tier Project Review."""

from datetime import date, timedelta
from app.modules.org.models import Department, Employee
from tests.helpers import API, DEVHEAD, FE, ABC, SUPPORT, eid, make, do, ok


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
