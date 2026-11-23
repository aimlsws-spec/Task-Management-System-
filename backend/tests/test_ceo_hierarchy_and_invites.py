"""Tests for CEO and Owner Employee Hierarchy management and Employee Invitations scoping.

Rules:
- CEO can create and manage employee hierarchy strictly for companies assigned/authorized by Owner.
- CEO cannot manage companies or employees outside the Owner-assigned scope (403 Forbidden).
- CEO cannot invite roles at or above CEO rank (Owner, CEO) (403 Forbidden).
- CEO can invite employees/managers for authorized companies, but not unauthorized companies (403 Forbidden).
- Owner has unrestricted authority across all companies.
"""

import pytest
from sqlalchemy import select

from app.modules.auth.models import User
from app.modules.auth.service import hash_password
from app.modules.org.models import Company, CompanyCEO, Department, Employee, ReportingRelationship
from app.modules.rbac.models import Role, UserRole
from tests.conftest import login

API = "/api/v1"
PW = "Demo@12345!"


def test_ceo_can_manage_hierarchy_only_for_authorized_company(client, as_user, seeded):
    # Setup: 2 companies, 1 CEO authorized only for company 2
    with seeded() as s:
        # Create company 2
        c2 = Company(name="Authorized Corp", code="auth-corp", is_active=True)
        s.add(c2)
        s.flush()

        # Create department for company 2
        d2 = Department(name="Auth Eng", code="AUTH-ENG", company_id=c2.id, self_service=True)
        s.add(d2)
        s.flush()

        # Create CEO user & employee authorized for company 2
        ceo_user = User(email="ceo_c2@auth.example", password_hash=hash_password(PW), is_active=True)
        s.add(ceo_user)
        s.flush()
        ceo_role = s.scalar(select(Role).where(Role.code == "ceo"))
        s.add(UserRole(user_id=ceo_user.id, role_id=ceo_role.id))
        s.add(CompanyCEO(company_id=c2.id, user_id=ceo_user.id))
        ceo_emp = Employee(
            user_id=ceo_user.id, employee_code="EMP-CEO2", full_name="CEO Two",
            department_id=d2.id, company_id=c2.id, status="active",
        )
        s.add(ceo_emp)

        # Create 2 employees in Company 2
        u_mgr = User(email="mgr_c2@auth.example", password_hash=hash_password(PW), is_active=True)
        s.add(u_mgr)
        s.flush()
        mgr_emp = Employee(
            user_id=u_mgr.id, employee_code="EMP-MGR2", full_name="Manager Two",
            department_id=d2.id, company_id=c2.id, status="active",
        )
        s.add(mgr_emp)

        u_dev = User(email="dev_c2@auth.example", password_hash=hash_password(PW), is_active=True)
        s.add(u_dev)
        s.flush()
        dev_emp = Employee(
            user_id=u_dev.id, employee_code="EMP-DEV2", full_name="Dev Two",
            department_id=d2.id, company_id=c2.id, status="active",
        )
        s.add(dev_emp)
        s.commit()

        c2_id = c2.id
        mgr_id = mgr_emp.id
        dev_id = dev_emp.id
        ceo_emp_id = ceo_emp.id

    # Find an employee and owner in Company 1 (from seeded demo org)
    with seeded() as s:
        emp_c1 = s.scalar(
            select(Employee)
            .join(UserRole, UserRole.user_id == Employee.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Employee.company_id == 1, Role.code == "employee")
        )
        emp_c1_id = emp_c1.id
        owner_c1 = s.scalar(
            select(Employee)
            .join(UserRole, UserRole.user_id == Employee.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Employee.company_id == 1, Role.code == "owner")
        )
        owner_c1_id = owner_c1.id

    # CEO Two headers
    h_ceo = login(client, "ceo_c2@auth.example", PW)

    # 1. CEO Two CAN set Dev Two's manager to Manager Two (same authorized company)
    r = client.post(
        f"{API}/hierarchy/relationships",
        headers=h_ceo,
        json={"employee_id": dev_id, "reports_to_id": mgr_id},
    )
    assert r.status_code == 204

    # Verify relationship was recorded
    with seeded() as s:
        rel = s.scalar(
            select(ReportingRelationship).where(
                ReportingRelationship.employee_id == dev_id,
                ReportingRelationship.effective_to.is_(None),
            )
        )
        assert rel is not None and rel.reports_to_id == mgr_id

    # 2. CEO Two CANNOT manage employee in Company 1 (outside authorized scope -> 403 Forbidden)
    r = client.post(
        f"{API}/hierarchy/relationships",
        headers=h_ceo,
        json={"employee_id": emp_c1_id, "reports_to_id": mgr_id},
    )
    assert r.status_code == 403, r.text
    assert "authorized companies" in r.text.lower()

    # 3. CEO Two CANNOT manage someone who outranks them (Owner -> 403 Forbidden)
    r = client.post(
        f"{API}/hierarchy/relationships",
        headers=h_ceo,
        json={"employee_id": owner_c1_id, "reports_to_id": mgr_id},
    )
    assert r.status_code == 403, r.text
    assert "outranks you" in r.text.lower()

    # 4. CEO Two CANNOT assign a manager from an unauthorized company (Company 1) to an employee in Company 2
    r = client.post(
        f"{API}/hierarchy/relationships",
        headers=h_ceo,
        json={"employee_id": dev_id, "reports_to_id": emp_c1_id},
    )
    assert r.status_code == 403, r.text
    assert "authorized companies" in r.text.lower()

    # 4. Cycle prevention: Manager Two reporting to Dev Two would create a cycle (since Dev Two reports to Manager Two)
    r = client.post(
        f"{API}/hierarchy/relationships",
        headers=h_ceo,
        json={"employee_id": mgr_id, "reports_to_id": dev_id},
    )
    assert r.status_code == 409
    assert "HIERARCHY_CYCLE" in r.text

    # 5. Hierarchy tree: CEO Two querying authorized company gets tree
    r = client.get(f"{API}/hierarchy/tree", headers=h_ceo, params={"company_id": c2_id})
    assert r.status_code == 200
    names = {n["full_name"] for n in r.json()}
    assert "CEO Two" in names or "Manager Two" in names

    # 6. Hierarchy tree: CEO Two querying unauthorized company gets empty tree
    r = client.get(f"{API}/hierarchy/tree", headers=h_ceo, params={"company_id": 1})
    assert r.status_code == 200
    assert r.json() == []


def test_ceo_can_invite_employees_only_for_authorized_company(client, as_user, seeded):
    # Setup company 3 and a CEO authorized for company 3
    with seeded() as s:
        c3 = Company(name="Inv Company", code="inv-corp", is_active=True)
        s.add(c3)
        s.flush()
        d3 = Department(name="Inv Dept", code="INV-DEPT", company_id=c3.id, self_service=True)
        s.add(d3)
        s.flush()

        ceo3_user = User(email="ceo3@inv.example", password_hash=hash_password(PW), is_active=True)
        s.add(ceo3_user)
        s.flush()
        ceo_role = s.scalar(select(Role).where(Role.code == "ceo"))
        s.add(UserRole(user_id=ceo3_user.id, role_id=ceo_role.id))
        s.add(CompanyCEO(company_id=c3.id, user_id=ceo3_user.id))
        ceo3_emp = Employee(
            user_id=ceo3_user.id, employee_code="EMP-CEO3", full_name="CEO Three",
            department_id=d3.id, company_id=c3.id, status="active",
        )
        s.add(ceo3_emp)
        s.commit()
        c3_id = c3.id

    h_ceo = login(client, "ceo3@inv.example", PW)

    # 1. CEO CAN invite an employee for authorized company 3
    r = client.post(
        f"{API}/role-invites",
        headers=h_ceo,
        json={"email": "new_staff@inv.example", "role_code": "employee", "company_id": c3_id},
    )
    assert r.status_code == 201

    # 2. CEO CANNOT invite an employee for company 1 (outside authorized scope -> 403 Forbidden)
    r = client.post(
        f"{API}/role-invites",
        headers=h_ceo,
        json={"email": "hacker@inv.example", "role_code": "employee", "company_id": 1},
    )
    assert r.status_code == 403, r.text

    # 3. CEO CANNOT invite an Owner (rank >= CEO -> 403 Forbidden)
    r = client.post(
        f"{API}/role-invites",
        headers=h_ceo,
        json={"email": "owner_wannabe@inv.example", "role_code": "owner", "company_id": c3_id},
    )
    assert r.status_code == 403, r.text

    # 4. CEO CANNOT invite another CEO (rank >= CEO -> 403 Forbidden)
    r = client.post(
        f"{API}/role-invites",
        headers=h_ceo,
        json={"email": "ceo_peer@inv.example", "role_code": "ceo", "company_id": c3_id},
    )
    assert r.status_code == 403, r.text

    # 5. Owner CAN invite to any company and any role
    r = client.post(
        f"{API}/role-invites",
        headers=as_user("owner"),
        json={"email": "owner_invited_ceo@inv.example", "role_code": "ceo", "company_id": c3_id},
    )
    assert r.status_code == 201


def test_ceo_can_create_departments_and_employees_in_authorized_company(client, as_user, seeded):
    # Setup company 4 and CEO authorized for company 4
    with seeded() as s:
        c4 = Company(name="Dept Co", code="dept-co", is_active=True)
        s.add(c4)
        s.flush()
        d4_gen = Department(name="Dept Co General", code="GEN-4", company_id=c4.id, self_service=True)
        s.add(d4_gen)
        s.flush()

        ceo4_user = User(email="ceo4@dept.example", password_hash=hash_password(PW), is_active=True)
        s.add(ceo4_user)
        s.flush()
        ceo_role = s.scalar(select(Role).where(Role.code == "ceo"))
        s.add(UserRole(user_id=ceo4_user.id, role_id=ceo_role.id))
        s.add(CompanyCEO(company_id=c4.id, user_id=ceo4_user.id))
        ceo4_emp = Employee(
            user_id=ceo4_user.id, employee_code="EMP-CEO4", full_name="CEO Four",
            department_id=d4_gen.id, company_id=c4.id, status="active",
        )
        s.add(ceo4_emp)
        s.commit()
        c4_id = c4.id
        d4_gen_id = d4_gen.id

    h_ceo = login(client, "ceo4@dept.example", PW)

    # 1. CEO can create department for authorized company without passing company_id (auto-defaults)
    r = client.post(
        f"{API}/departments",
        headers=h_ceo,
        json={"name": "Engineering 4", "code": "ENG-4"},
    )
    assert r.status_code == 201
    new_dept_id = r.json()["id"]
    assert r.json()["company_id"] == c4_id

    # 2. CEO CANNOT create department in unauthorized company 1
    r = client.post(
        f"{API}/departments",
        headers=h_ceo,
        json={"name": "Hacked Dept", "code": "HACK-1", "company_id": 1},
    )
    assert r.status_code == 403, r.text

    # 3. CEO can create an employee in authorized company and assign 'manager' role
    r = client.post(
        f"{API}/employees",
        headers=h_ceo,
        json={
            "email": "mgr4@dept.example",
            "full_name": "Manager Four",
            "department_id": new_dept_id,
            "company_id": c4_id,
            "temp_password": PW,
            "role_codes": ["manager"],
        },
    )
    assert r.status_code == 201
    new_emp_id = r.json()["id"]

    # 4. CEO CANNOT assign 'ceo' or 'owner' role to a newly created employee (rank >= CEO)
    r = client.post(
        f"{API}/employees",
        headers=h_ceo,
        json={
            "email": "rogue_ceo@dept.example",
            "full_name": "Rogue CEO",
            "department_id": new_dept_id,
            "company_id": c4_id,
            "temp_password": PW,
            "role_codes": ["ceo"],
        },
    )
    assert r.status_code == 403, r.text

    # 5. CEO can set department leaders (Head and SubHead) in authorized company
    r = client.put(
        f"{API}/departments/{new_dept_id}/leaders",
        headers=h_ceo,
        json={"head_employee_ids": [new_emp_id], "sub_head_employee_ids": []},
    )
    assert r.status_code == 200

    # 6. CEO CANNOT set leaders on a department in unauthorized company 1
    with seeded() as s:
        dept_c1 = s.scalar(select(Department).where(Department.company_id == 1))
        dept_c1_id = dept_c1.id

    r = client.put(
        f"{API}/departments/{dept_c1_id}/leaders",
        headers=h_ceo,
        json={"head_employee_ids": [new_emp_id], "sub_head_employee_ids": []},
    )
    assert r.status_code == 403, r.text

