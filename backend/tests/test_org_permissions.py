"""Scope/permission behaviour for organization features. Organization setup (employees, departments,
hierarchy, roles, settings) belongs to the ADMIN role only; Owner/CEO/Manager do work, not setup."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.audit.models import ActivityLog
from app.modules.org.models import Department, Employee, ReportingRelationship
from app.modules.rbac.models import Permission, Role, RolePermission

API = "/api/v1"


def emp_id(seeded, code):
    with seeded() as s:
        return s.scalar(select(Employee.id).where(Employee.employee_code == code))


def dept_id(seeded, code):
    with seeded() as s:
        return s.scalar(select(Department.id).where(Department.code == code))


def names(resp):
    return {e["full_name"] for e in resp.json()["items"]}


def delegate(seeded, role_code, perm_codes, scope="organization"):
    """Simulate an Admin delegating permissions to another role (to prove the rank guard still holds)."""
    with seeded() as s:
        role = s.scalar(select(Role).where(Role.code == role_code))
        for code in perm_codes:
            perm = s.scalar(select(Permission).where(Permission.code == code))
            s.add(RolePermission(role_id=role.id, permission_id=perm.id, scope=scope))
        s.commit()


def new_emp(seeded, **over):
    return {
        "email": "new.hire@demo.example.com", "full_name": "New Hire", "employee_code": "SW-K7M2Q9",
        "department_id": dept_id(seeded, "DEV"), "temp_password": "Temp#Pass12345", "job_title": "Backend Developer",
    } | over  # fmt: skip


# ---------- visibility scopes ----------


def test_owner_and_ceo_see_everyone(client, as_user):
    for who in ("owner", "ceo", "admin"):
        assert len(client.get(f"{API}/employees", headers=as_user(who)).json()["items"]) == 14


def test_manager_sees_only_reporting_subtree_plus_self(client, as_user):
    got = names(client.get(f"{API}/employees", headers=as_user("manager")))
    assert "Demo Owner" not in got and "Demo CEO" not in got and "Demo Admin" not in got
    assert {"Demo Manager", "ABC", "Developers Head", "Support Agent", "Accountant"} <= got
    assert len(got) == 11


def test_department_head_sees_only_own_department(client, as_user):
    assert names(client.get(f"{API}/employees", headers=as_user("devhead"))) == {"Developers Head", "ABC", "Frontend Dev"}
    assert names(client.get(f"{API}/employees", headers=as_user("hrhead"))) == {"HR Head", "HR Executive"}


def test_employee_sees_only_self(client, as_user):
    assert names(client.get(f"{API}/employees", headers=as_user("abc"))) == {"ABC"}


def test_out_of_scope_employee_is_404_not_403(client, as_user, seeded):
    hr_exec = emp_id(seeded, "EMP-0009")
    assert client.get(f"{API}/employees/{hr_exec}", headers=as_user("devhead")).status_code == 404
    assert client.get(f"{API}/employees/{hr_exec}", headers=as_user("hrhead")).status_code == 200


def test_support_sales_accounts_are_managed_directly_by_manager(client, as_user):
    assert {"Support Agent", "Sales Executive", "Accountant"} <= names(client.get(f"{API}/employees", headers=as_user("manager")))


# ---------- organization setup is Admin-only ----------


@pytest.mark.parametrize("who", ["owner", "ceo", "manager", "devhead", "abc"])
def test_only_admin_can_create_employees(client, as_user, seeded, who):
    assert client.post(f"{API}/employees", headers=as_user(who), json=new_emp(seeded)).status_code == 403


def test_admin_creates_employee_with_hierarchy_and_audit(client, as_user, seeded):
    boss = emp_id(seeded, "EMP-0004")
    r = client.post(f"{API}/employees", headers=as_user("admin"), json=new_emp(seeded, reports_to_id=boss))
    assert r.status_code == 201, r.text
    assert r.json()["reports_to_id"] == boss and r.json()["roles"] == ["employee"]
    assert "New Hire" not in names(client.get(f"{API}/employees", headers=as_user("hrhead")))
    with seeded() as s:
        assert s.scalar(select(ActivityLog).where(ActivityLog.action == "EMPLOYEE_CREATED"))


def test_new_employee_must_change_password(client, as_user, seeded):
    client.post(f"{API}/employees", headers=as_user("admin"), json=new_emp(seeded))
    r = client.post(f"{API}/auth/login", json={"email": "new.hire@demo.example.com", "password": "Temp#Pass12345"})
    assert r.json()["must_change_password"] is True


def test_duplicate_email_rejected(client, as_user, seeded):
    r = client.post(f"{API}/employees", headers=as_user("admin"), json=new_emp(seeded, email="abc@demo.example.com"))
    assert r.status_code == 409


def test_unknown_field_rejected_mass_assignment(client, as_user, seeded):
    r = client.post(f"{API}/employees", headers=as_user("admin"), json=new_emp(seeded) | {"is_active": False, "password_hash": "x"})
    assert r.status_code == 422


def test_roles_and_settings_are_admin_only(client, as_user):
    for who in ("owner", "ceo", "manager"):
        assert client.get(f"{API}/roles", headers=as_user(who)).status_code == 403
        assert client.get(f"{API}/admin/settings", headers=as_user(who)).status_code == 403
    assert client.get(f"{API}/roles", headers=as_user("admin")).status_code == 200
    assert client.get(f"{API}/admin/settings", headers=as_user("admin")).status_code == 200


def test_admin_can_grant_any_role_and_change_forces_relogin(client, as_user, seeded):
    h = as_user("abc")
    abc = emp_id(seeded, "EMP-0007")
    r = client.patch(f"{API}/employees/{abc}", headers=as_user("admin"), json={"role_codes": ["department_head"]})
    assert r.status_code == 200 and r.json()["roles"] == ["department_head"]
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401  # session revoked -> new permissions apply


def test_admin_edits_role_permissions_and_it_is_audited(client, as_user, seeded):
    h = as_user("admin")
    with seeded() as s:
        rid = s.scalar(select(Role.id).where(Role.code == "department_head"))
    r = client.put(f"{API}/roles/{rid}/permissions", headers=h, json={"grants": [{"permission": "task.view", "scope": "department"}]})
    assert r.status_code == 200 and r.json()["permissions"] == {"task.view": "department"}
    assert "task.create" not in client.get(f"{API}/auth/me", headers=as_user("devhead")).json()["permissions"]
    bad = client.put(f"{API}/roles/{rid}/permissions", headers=h, json={"grants": [{"permission": "task.view", "scope": "galaxy"}]})
    assert bad.status_code == 422
    with seeded() as s:
        assert s.scalar(select(ActivityLog).where(ActivityLog.action == "ROLE_PERMISSIONS_CHANGED"))


# ---------- rank guard (nobody manages someone who outranks them) ----------


def test_delegated_org_permissions_still_cannot_touch_higher_ranks(client, as_user, seeded):
    delegate(seeded, "ceo", ["employee.manage", "hierarchy.manage"])
    owner, ceo = emp_id(seeded, "EMP-0001"), emp_id(seeded, "EMP-0002")
    h = as_user("ceo")
    assert client.post(f"{API}/employees/{owner}/deactivate", headers=h).status_code == 403
    assert client.patch(f"{API}/employees/{owner}", headers=h, json={"job_title": "x"}).status_code == 403
    r = client.post(f"{API}/hierarchy/relationships", headers=h, json={"employee_id": owner, "reports_to_id": ceo})
    assert r.status_code == 403
    abc = emp_id(seeded, "EMP-0007")  # lower ranks are still manageable
    assert client.patch(f"{API}/employees/{abc}", headers=h, json={"job_title": "Lead AI/ML"}).status_code == 200


def test_delegated_role_manage_still_cannot_touch_higher_ranks(client, as_user, seeded):
    delegate(seeded, "ceo", ["role.manage"])
    owner_user_id = client.get(f"{API}/auth/me", headers=as_user("owner")).json()["user"]["id"]
    h = as_user("ceo")
    assert client.get(f"{API}/roles", headers=h).status_code == 200
    assert client.put(f"{API}/users/{owner_user_id}/roles", headers=h, json={"role_codes": ["employee"]}).status_code == 403


def test_owner_and_ceo_hold_no_organization_setup_permissions(client, as_user):
    for who in ("owner", "ceo"):
        p = client.get(f"{API}/auth/me", headers=as_user(who)).json()["permissions"]
        assert not {"employee.manage", "department.manage", "hierarchy.manage", "role.manage", "settings.manage"} & set(p)


# ---------- hierarchy ----------


def test_cycle_is_rejected(client, as_user, seeded):
    owner, ceo = emp_id(seeded, "EMP-0001"), emp_id(seeded, "EMP-0002")
    h = as_user("admin")
    r = client.post(f"{API}/hierarchy/relationships", headers=h, json={"employee_id": owner, "reports_to_id": ceo})
    assert r.status_code == 409 and r.json()["code"] == "HIERARCHY_CYCLE"
    assert client.post(f"{API}/hierarchy/relationships", headers=h, json={"employee_id": ceo, "reports_to_id": ceo}).status_code == 409


def test_manager_change_keeps_history(client, as_user, seeded):
    support, hr_head = emp_id(seeded, "EMP-0011"), emp_id(seeded, "EMP-0005")
    h = as_user("admin")
    assert client.post(f"{API}/hierarchy/relationships", headers=h, json={"employee_id": support, "reports_to_id": hr_head}).status_code == 204
    hist = client.get(f"{API}/hierarchy/relationships", params={"employee_id": support}, headers=h).json()
    assert len(hist) == 2 and hist[0]["effective_to"] is not None and hist[1]["effective_to"] is None
    # Dept-head scope is DEPARTMENT membership: a reporting-line change alone does not leak a Support employee
    # to the HR Head, while the Manager (team scope, still above in the tree) keeps seeing them.
    assert "Support Agent" not in names(client.get(f"{API}/employees", headers=as_user("hrhead")))
    assert "Support Agent" in names(client.get(f"{API}/employees", headers=as_user("manager")))


def test_db_forbids_two_active_primary_managers(seeded):
    a, c = emp_id(seeded, "EMP-0007"), emp_id(seeded, "EMP-0005")
    with seeded() as s:
        s.add(ReportingRelationship(employee_id=a, reports_to_id=c))  # abc already has an active manager
        with pytest.raises(IntegrityError):
            s.flush()


def test_hierarchy_tree_is_scoped(client, as_user):
    def flat(nodes):
        out = []
        for n in nodes:
            out += [n["full_name"], *flat(n["children"])]
        return out

    owner_tree = client.get(f"{API}/hierarchy/tree", headers=as_user("owner")).json()
    assert len(flat(owner_tree)) == 14 and {n["full_name"] for n in owner_tree} == {"Demo Owner", "Demo Admin"}
    assert set(flat(client.get(f"{API}/hierarchy/tree", headers=as_user("devhead")).json())) == {"Developers Head", "ABC", "Frontend Dev"}


# ---------- offboarding ----------


def test_deactivation_blocks_login_and_kills_session(client, as_user, seeded):
    h = as_user("abc")
    abc = emp_id(seeded, "EMP-0007")
    r = client.post(f"{API}/employees/{abc}/deactivate", headers=as_user("admin"))
    assert r.status_code == 200 and "orphaned_tasks" in r.json()
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "abc@demo.example.com", "password": "Demo@12345!"}).status_code == 401


def test_cannot_deactivate_self(client, as_user, seeded):
    admin = emp_id(seeded, "EMP-0000")
    assert client.post(f"{API}/employees/{admin}/deactivate", headers=as_user("admin")).status_code == 409


# ---------- departments (Admin only: add / edit / delete / heads) ----------


def test_departments_list_open_to_all_but_manage_admin_only(client, as_user):
    assert client.get(f"{API}/departments", headers=as_user("abc")).status_code == 200
    for who in ("owner", "ceo", "manager", "devhead"):
        assert client.post(f"{API}/departments", headers=as_user(who), json={"name": "Legal", "code": "LEG"}).status_code == 403
    assert client.post(f"{API}/departments", headers=as_user("admin"), json={"name": "Legal", "code": "LEG"}).status_code == 201


def test_admin_edits_and_deletes_empty_department(client, as_user):
    h = as_user("admin")
    d = client.post(f"{API}/departments", headers=h, json={"name": "Legal", "code": "LEG"}).json()
    r = client.patch(f"{API}/departments/{d['id']}", headers=h, json={"name": "Legal & Compliance", "self_service": False})
    assert r.status_code == 200 and r.json()["name"] == "Legal & Compliance" and r.json()["self_service"] is False
    assert client.delete(f"{API}/departments/{d['id']}", headers=h).status_code == 204
    assert d["id"] not in [x["id"] for x in client.get(f"{API}/departments", headers=h).json()]


def test_cannot_delete_department_with_employees_or_system_department(client, as_user, seeded):
    h = as_user("admin")
    r = client.delete(f"{API}/departments/{dept_id(seeded, 'DEV')}", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "DEPARTMENT_NOT_EMPTY"
    with seeded() as s:
        s.add(Department(name="Temp", code="TMP", is_system=True))
        s.commit()
    r = client.delete(f"{API}/departments/{dept_id(seeded, 'TMP')}", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "SYSTEM_DEPARTMENT"


def test_setting_head_with_regroup_moves_members_under_new_head(client, as_user, seeded):
    fe, abc = emp_id(seeded, "EMP-0008"), emp_id(seeded, "EMP-0007")
    h = as_user("admin")
    r = client.put(f"{API}/departments/{dept_id(seeded, 'DEV')}/head", headers=h, json={"head_employee_id": fe, "regroup_members": True})
    assert r.status_code == 200 and r.json()["head_employee_id"] == fe and r.json()["members_moved"] == 1
    assert client.get(f"{API}/employees/{abc}", headers=h).json()["reports_to_id"] == fe
    with seeded() as s:
        actions = {a.action for a in s.scalars(select(ActivityLog))}
    assert {"DEPARTMENT_HEAD_CHANGED", "DEPARTMENT_REGROUPED"} <= actions


def test_head_change_without_regroup_leaves_members_alone(client, as_user, seeded):
    fe, abc, dev_head = emp_id(seeded, "EMP-0008"), emp_id(seeded, "EMP-0007"), emp_id(seeded, "EMP-0004")
    h = as_user("admin")
    client.put(f"{API}/departments/{dept_id(seeded, 'DEV')}/head", headers=h, json={"head_employee_id": fe})
    assert client.get(f"{API}/employees/{abc}", headers=h).json()["reports_to_id"] == dev_head


def test_moving_employee_to_department_regroups_under_its_head_or_manager(client, as_user, seeded):
    abc, hr_head, manager = emp_id(seeded, "EMP-0007"), emp_id(seeded, "EMP-0005"), emp_id(seeded, "EMP-0003")
    h = as_user("admin")
    client.patch(f"{API}/employees/{abc}", headers=h, json={"department_id": dept_id(seeded, "HR")})
    assert client.get(f"{API}/employees/{abc}", headers=h).json()["reports_to_id"] == hr_head
    client.patch(f"{API}/employees/{abc}", headers=h, json={"department_id": dept_id(seeded, "ACC")})  # no head
    assert client.get(f"{API}/employees/{abc}", headers=h).json()["reports_to_id"] == manager


def test_cannot_move_a_department_head_out_without_changing_head(client, as_user, seeded):
    dev_head = emp_id(seeded, "EMP-0004")
    r = client.patch(f"{API}/employees/{dev_head}", headers=as_user("admin"), json={"department_id": dept_id(seeded, "HR")})
    assert r.status_code == 409 and r.json()["code"] == "IS_DEPARTMENT_HEAD"


# ---------- calendar / settings / audit ----------


def test_work_calendar_endpoint(client, as_user):
    r = client.get(f"{API}/work-calendar", params={"from_": "2026-11-13", "to": "2026-11-16"}, headers=as_user("abc"))
    days = {d["date"]: d for d in r.json()}
    assert days["2026-11-14"]["is_working"] is False and days["2026-11-14"]["reason"] == "nth_weekday_off"
    assert days["2026-11-15"]["is_working"] is False
    assert days["2026-11-16"]["working_hours"] == 8.5


def test_holiday_management_admin_only(client, as_user):
    body = {"date": "2026-11-17", "name": "Festival"}
    for who in ("owner", "manager"):
        assert client.post(f"{API}/holidays", headers=as_user(who), json=body).status_code == 403
    assert client.post(f"{API}/holidays", headers=as_user("admin"), json=body).status_code == 201
    r = client.get(f"{API}/work-calendar", params={"from_": "2026-11-17", "to": "2026-11-17"}, headers=as_user("abc"))
    assert r.json()[0]["is_working"] is False


def test_settings_validation(client, as_user):
    h = as_user("admin")
    assert client.put(f"{API}/admin/settings", headers=h, json={"company_timezone": "Mars/Base"}).status_code == 422
    assert client.put(f"{API}/admin/settings", headers=h, json={"eod_time": "25:99"}).status_code == 422
    r = client.put(f"{API}/admin/settings", headers=h,
                   json={"company_timezone": "Asia/Dubai", "eod_time": "18:30"})  # fmt: skip
    assert r.status_code == 200 and r.json()["company_timezone"] == "Asia/Dubai" and r.json()["eod_time"] == "18:30"


def test_audit_log_visibility(client, as_user):
    assert client.get(f"{API}/admin/audit-logs", headers=as_user("manager")).status_code == 403
    client.post(f"{API}/departments", headers=as_user("admin"), json={"name": "Legal", "code": "LEG"})
    for who in ("ceo", "owner"):  # ADR 002: the audit log is for the Admin alone
        assert client.get(f"{API}/admin/audit-logs", headers=as_user(who)).status_code == 403
    r = client.get(f"{API}/admin/audit-logs", params={"action": "DEPARTMENT_CREATED"}, headers=as_user("admin"))
    assert r.status_code == 200 and r.json()["total"] == 1


def test_authz_denials_are_logged(client, as_user, seeded):
    client.post(f"{API}/employees", headers=as_user("manager"), json=new_emp(seeded))
    with seeded() as s:
        assert s.scalar(select(ActivityLog).where(ActivityLog.action == "AUTHZ_DENIED"))
