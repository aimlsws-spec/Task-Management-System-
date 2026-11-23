from datetime import date

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.security import hash_password, validate_password_policy
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.auth.service import revoke_all_sessions
from app.modules.notifications import direct
from app.modules.org import codes
from app.modules.org.models import Department, Employee, ReportingRelationship
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.policy import Principal, subtree_ids, user_max_rank

PENDING = "pending_setup"  # signed up but has not yet chosen department + designation
DEFAULT_MANAGER_ROLE = "manager"  # seed role code that receives people whose department has no head


def default_manager_id(db: Session, dept: Department, exclude_employee_id: int | None = None) -> int | None:
    """Who a person in `dept` reports to: the department head, else the company Manager (Support/Sales/Accounts)."""
    head = dept.head_employee_id
    if head and head != exclude_employee_id:
        h = db.get(Employee, head)
        if h is not None and h.status != "inactive":
            return head
    return db.scalar(
        select(Employee.id)
        .join(UserRole, UserRole.user_id == Employee.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == DEFAULT_MANAGER_ROLE, Employee.status != "inactive", Employee.id != (exclude_employee_id or 0))
        .order_by(Employee.id)
        .limit(1)
    )


# ---------- departments ----------


def create_department(db: Session, p: Principal, name: str, code: str, parent_id: int | None, request: Request, company_id: int = 1) -> Department:
    if not p.can_access_company(company_id):
        raise Forbidden("You cannot manage departments for this company")
    if db.scalar(select(Department.id).where((Department.name == name) | (Department.code == code))):
        raise Conflict("DEPARTMENT_EXISTS", "A department with this name or code already exists")
    if parent_id is not None and db.get(Department, parent_id) is None:
        raise AppError("INVALID_PARENT", "Parent department not found", 422)
    d = Department(name=name, code=code.upper(), parent_id=parent_id, company_id=company_id)
    db.add(d)
    db.flush()
    audit.log(db, p.user.id, "DEPARTMENT_CREATED", "department", d.id, after={"name": name, "code": d.code, "company_id": company_id}, request=request)
    return d


def set_department_qa(db: Session, p: Principal, dept: Department, qa_employee_id: int | None, request: Request) -> None:
    if not p.can_access_company(getattr(dept, "company_id", 1)):
        raise Forbidden("You cannot manage departments for this company")
    if qa_employee_id is not None:
        emp = db.get(Employee, qa_employee_id)
        if emp is None or emp.status == "inactive":
            raise AppError("INVALID_EMPLOYEE", "Choose an active employee", 422)
    before = dept.qa_employee_id
    dept.qa_employee_id = qa_employee_id
    db.flush()
    audit.log(db, p.user.id, "DEPARTMENT_QA_SET", "department", dept.id,
              before={"qa_employee_id": before}, after={"qa_employee_id": qa_employee_id}, request=request)  # fmt: skip


def set_department_head(db: Session, p: Principal, dept: Department, head_employee_id: int | None, request: Request, regroup: bool = False) -> int:
    if not p.can_access_company(getattr(dept, "company_id", 1)):
        raise Forbidden("You cannot manage departments for this company")
    """Sets the head. With regroup=True, members of the department are moved under the new head. Returns #moved."""
    if head_employee_id is not None:
        emp = db.get(Employee, head_employee_id)
        if emp is None or emp.status == "inactive":
            raise AppError("INVALID_HEAD", "Head must be an active employee", 422)
    before = dept.head_employee_id
    dept.head_employee_id = head_employee_id
    db.flush()
    _sync_head_roles(db, p, dept, before, head_employee_id)
    audit.log(db, p.user.id, "DEPARTMENT_HEAD_CHANGED", "department", dept.id,
              before={"head_employee_id": before}, after={"head_employee_id": head_employee_id}, request=request)  # fmt: skip
    if regroup and head_employee_id:
        from app.modules.org.admin_service import regroup_department_under_head

        return regroup_department_under_head(db, p, dept, request)
    return 0


HEAD_ROLE = "department_head"
SUB_HEAD_ROLE = "sub_head"


def set_department_sub_head(db: Session, p: Principal, dept: Department, sub_head_employee_id: int | None, request: Request) -> None:
    if not p.can_access_company(getattr(dept, "company_id", 1)):
        raise Forbidden("You cannot manage departments for this company")
    if sub_head_employee_id is not None:
        emp = db.get(Employee, sub_head_employee_id)
        if emp is None or emp.status == "inactive":
            raise AppError("INVALID_SUB_HEAD", "Sub-head must be an active employee", 422)
    before = dept.sub_head_employee_id
    dept.sub_head_employee_id = sub_head_employee_id
    db.flush()
    _sync_sub_head_roles(db, p, dept, before, sub_head_employee_id)
    audit.log(db, p.user.id, "DEPARTMENT_SUB_HEAD_CHANGED", "department", dept.id,
              before={"sub_head_employee_id": before}, after={"sub_head_employee_id": sub_head_employee_id}, request=request)


def _sync_sub_head_roles(db: Session, p: Principal, dept: Department, old_id: int | None, new_id: int | None) -> None:
    role = db.scalar(select(Role).where(Role.code == SUB_HEAD_ROLE))
    if role is None or old_id == new_id:
        return
    if new_id is not None:
        user_id = db.get(Employee, new_id).user_id
        has = db.scalar(select(UserRole.user_id).where(UserRole.user_id == user_id, UserRole.role_id == role.id))
        if user_max_rank(db, user_id) < role.rank and not has:
            db.add(UserRole(user_id=user_id, role_id=role.id, granted_by=p.user.id))
            db.flush()
            revoke_all_sessions(db, db.get(User, user_id))
    if old_id is not None and not db.scalar(select(Department.id).where(Department.sub_head_employee_id == old_id, Department.id != dept.id)):
        user_id = db.get(Employee, old_id).user_id
        removed = db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.role_id == role.id).delete()
        if removed:
            if not db.scalar(select(UserRole.user_id).where(UserRole.user_id == user_id)):
                employee = db.scalar(select(Role).where(Role.code == "employee"))
                if employee:
                    db.add(UserRole(user_id=user_id, role_id=employee.id, granted_by=p.user.id))
            db.flush()
            revoke_all_sessions(db, db.get(User, user_id))


def _sync_head_roles(db: Session, p: Principal, dept: Department, old_id: int | None, new_id: int | None) -> None:
    """Naming a head gives them the Department Head role (so the hierarchy works); the person they replace loses it
    unless they still head another department. Higher roles (Manager, CEO, ...) are never touched or downgraded."""
    role = db.scalar(select(Role).where(Role.code == HEAD_ROLE))
    if role is None or old_id == new_id:
        return
    if new_id is not None:
        user_id = db.get(Employee, new_id).user_id
        has = db.scalar(select(UserRole.user_id).where(UserRole.user_id == user_id, UserRole.role_id == role.id))
        if user_max_rank(db, user_id) < role.rank and not has:
            db.add(UserRole(user_id=user_id, role_id=role.id, granted_by=p.user.id))
            db.flush()
            revoke_all_sessions(db, db.get(User, user_id))  # sign in again to get the head's permissions
    if new_id is not None:
        new_emp = db.get(Employee, new_id)
        direct.head_named(db, db.get(User, new_emp.user_id).email, new_emp.user_id, dept.name)
    if old_id is not None and not db.scalar(select(Department.id).where(Department.head_employee_id == old_id, Department.id != dept.id)):
        user_id = db.get(Employee, old_id).user_id
        removed = db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.role_id == role.id).delete()
        if removed:
            if not db.scalar(select(UserRole.user_id).where(UserRole.user_id == user_id)):
                employee = db.scalar(select(Role).where(Role.code == "employee"))
                db.add(UserRole(user_id=user_id, role_id=employee.id, granted_by=p.user.id))
            db.flush()
            revoke_all_sessions(db, db.get(User, user_id))


# ---------- employees ----------


def current_manager_id(db: Session, employee_id: int) -> int | None:
    return db.scalar(
        select(ReportingRelationship.reports_to_id).where(
            ReportingRelationship.employee_id == employee_id,
            ReportingRelationship.relation_type == "primary",
            ReportingRelationship.effective_to.is_(None),
        )
    )


def role_codes(db: Session, user_id: int) -> list[str]:
    return sorted(db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)))


def employee_dict(db: Session, e: Employee) -> dict:
    u = db.get(User, e.user_id)
    return {
        "id": e.id, "user_id": e.user_id, "employee_code": e.employee_code, "full_name": e.full_name,
        "email": u.email, "phone": e.phone, "job_title": e.job_title, "department_id": e.department_id,
        "company_id": getattr(e, "company_id", 1),
        "status": e.status, "is_active": u.is_active, "daily_capacity_hours": float(e.daily_capacity_hours),
        "can_receive_tasks": e.can_receive_tasks, "roles": role_codes(db, e.user_id),
        "reports_to_id": current_manager_id(db, e.id),
    }  # fmt: skip


def _role_names(db: Session, codes: list[str]) -> list[str]:
    return list(db.scalars(select(Role.name).where(Role.code.in_(codes)).order_by(Role.rank.desc())))


def _assign_roles(db: Session, p: Principal, user: User, codes: list[str]) -> None:
    roles = db.scalars(select(Role).where(Role.code.in_(codes))).all() if codes else []
    if len(roles) != len(set(codes)):
        raise AppError("UNKNOWN_ROLE", "One or more roles do not exist", 422)
    for r in roles:
        if r.rank > p.rank and "admin" not in p.roles and "owner" not in p.roles:
            raise Forbidden("You cannot grant a role above your own rank")
    db.query(UserRole).filter(UserRole.user_id == user.id).delete()
    for r in roles:
        db.add(UserRole(user_id=user.id, role_id=r.id, granted_by=p.user.id))
    db.flush()  # autoflush is off; make the new roles visible to reads in this request


def create_employee(db: Session, p: Principal, data: dict, request: Request) -> Employee:
    email = data["email"].strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("EMAIL_EXISTS", "A user with this email already exists")
    code = codes.check_custom(db, data["employee_code"]) if (data.get("employee_code") or "").strip() else codes.generate(db)
    dept = db.get(Department, data["department_id"])
    if dept is None or not dept.is_active:
        raise AppError("INVALID_DEPARTMENT", "Department not found or inactive", 422)
    validate_password_policy(data["temp_password"])
    user = User(email=email, password_hash=hash_password(data["temp_password"]), must_change_password=True)
    db.add(user)
    db.flush()
    emp = Employee(
        user_id=user.id, employee_code=code, full_name=data["full_name"], phone=data.get("phone"),
        job_title=data.get("job_title"), department_id=dept.id, joined_on=data.get("joined_on") or date.today(),
    )  # fmt: skip
    db.add(emp)
    db.flush()
    _assign_roles(db, p, user, data.get("role_codes") or ["employee"])
    if data.get("reports_to_id") is not None:
        set_manager(db, p, emp.id, data["reports_to_id"], request, audit_it=False)
    names = list(db.scalars(select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)))
    direct.added_by_admin(db, email, user.id, emp.full_name, names, dept.name)
    audit.log(db, p.user.id, "EMPLOYEE_CREATED", "employee", emp.id,
              after={"email": email, "employee_code": emp.employee_code, "department_id": dept.id}, request=request)  # fmt: skip
    return emp


def guard_rank(db: Session, p: Principal, emp: Employee) -> None:
    """Nobody may modify, deactivate or re-point someone who outranks them (e.g. CEO -> Owner)."""
    if user_max_rank(db, emp.user_id) > p.rank:
        raise Forbidden("You cannot manage a user who outranks you")


def update_employee(db: Session, p: Principal, emp: Employee, data: dict, request: Request) -> None:
    guard_rank(db, p, emp)
    before = {k: getattr(emp, k) for k in data if k != "role_codes"}
    if "department_id" in data:
        dept = db.get(Department, data["department_id"])
        if dept is None or not dept.is_active:
            raise AppError("INVALID_DEPARTMENT", "Department not found or inactive", 422)
    dept_changed = "department_id" in data and data["department_id"] != emp.department_id
    if dept_changed and db.scalar(select(Department.id).where(Department.head_employee_id == emp.id)):
        raise Conflict("IS_DEPARTMENT_HEAD", "This person heads a department. Change the department head first.")
    for k, v in data.items():
        if k != "role_codes":
            setattr(emp, k, v)
    if dept_changed:
        new_dept = db.get(Department, emp.department_id)
        if emp.status == PENDING and not new_dept.is_system:
            emp.status = "active"
        # keep people grouped under the right head: department head, else the Manager
        set_manager(db, p, emp.id, default_manager_id(db, new_dept, emp.id), request, audit_it=False)
    if data.get("role_codes") is not None:
        old_roles = set(role_codes(db, emp.user_id))
        _assign_roles(db, p, db.get(User, emp.user_id), data["role_codes"])
        if set(data["role_codes"]) != old_roles:
            direct.role_changed(db, db.get(User, emp.user_id).email, emp.user_id, _role_names(db, data["role_codes"]))
        revoke_all_sessions(db, db.get(User, emp.user_id))  # permissions changed -> re-login
    audit.log(db, p.user.id, "EMPLOYEE_UPDATED", "employee", emp.id,
              before={k: str(v) for k, v in before.items()}, after={k: str(v) for k, v in data.items()}, request=request)  # fmt: skip


def deactivate_employee(db: Session, p: Principal, emp: Employee, request: Request) -> dict:
    guard_rank(db, p, emp)
    if p.employee is not None and p.employee.id == emp.id:
        raise AppError("CANNOT_DEACTIVATE_SELF", "You cannot deactivate yourself", 409)
    user = db.get(User, emp.user_id)
    user.is_active = False
    emp.status, emp.left_on = "inactive", date.today()
    revoke_all_sessions(db, user)
    heads = list(db.scalars(select(Department.id).where(Department.head_employee_id == emp.id)))
    reports = list(
        db.scalars(
            select(ReportingRelationship.employee_id).where(
                ReportingRelationship.reports_to_id == emp.id, ReportingRelationship.effective_to.is_(None)
            )
        )
    )
    audit.log(db, p.user.id, "EMPLOYEE_DEACTIVATED", "employee", emp.id, request=request)
    # `orphaned_tasks` is filled in Phase 3 when tasks exist; heads/reports need re-pointing by an admin now.
    return {"orphaned_tasks": [], "heads_departments": heads, "direct_reports": reports}


def reactivate_employee(db: Session, p: Principal, emp: Employee, request: Request) -> None:
    guard_rank(db, p, emp)
    user = db.get(User, emp.user_id)
    user.is_active = True
    emp.status, emp.left_on = "active", None
    audit.log(db, p.user.id, "EMPLOYEE_REACTIVATED", "employee", emp.id, request=request)


# ---------- hierarchy ----------


def set_manager(db: Session, p: Principal, employee_id: int, reports_to_id: int | None, request: Request, audit_it: bool = True) -> None:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise NotFound("Employee")
    guard_rank(db, p, emp)
    if reports_to_id is not None:
        boss = db.get(Employee, reports_to_id)
        if boss is None or boss.status == "inactive":
            raise AppError("INVALID_MANAGER", "Manager must be an active employee", 422)
        if reports_to_id == employee_id or reports_to_id in subtree_ids(db, employee_id):
            raise AppError("HIERARCHY_CYCLE", "This change would create a reporting cycle", 409)
    old = current_manager_id(db, employee_id)
    if old == reports_to_id:
        return
    now = clock.utcnow()
    if old is not None:
        row = db.scalar(
            select(ReportingRelationship).where(
                ReportingRelationship.employee_id == employee_id,
                ReportingRelationship.relation_type == "primary",
                ReportingRelationship.effective_to.is_(None),
            )
        )
        row.effective_to = now
        db.flush()  # free the unique "one active" slot before inserting the new row
    if reports_to_id is not None:
        db.add(ReportingRelationship(employee_id=employee_id, reports_to_id=reports_to_id, effective_from=now, created_by=p.user.id))
    db.flush()
    if audit_it:
        audit.log(db, p.user.id, "REPORTING_LINE_CHANGED", "employee", employee_id,
                  before={"reports_to_id": old}, after={"reports_to_id": reports_to_id}, request=request)  # fmt: skip


def hierarchy_tree(db: Session, visible_ids: set[int] | None, company_id: int | None = None) -> list[dict]:
    q = select(Employee).where(Employee.status != "inactive")
    if visible_ids is not None:
        q = q.where(Employee.id.in_(visible_ids))
    if company_id is not None:
        q = q.where(Employee.company_id == company_id)
    emps = {e.id: e for e in db.scalars(q)}
    links = {
        r.employee_id: r.reports_to_id
        for r in db.scalars(
            select(ReportingRelationship).where(
                ReportingRelationship.effective_to.is_(None), ReportingRelationship.relation_type == "primary"
            )
        )
    }
    nodes = {
        i: {
            "id": i,
            "full_name": e.full_name,
            "job_title": e.job_title,
            "department_id": e.department_id,
            "company_id": getattr(e, "company_id", 1),
            "children": [],
        }
        for i, e in emps.items()
    }
    roots = []
    for i, node in nodes.items():
        parent = links.get(i)
        if parent in nodes:
            nodes[parent]["children"].append(node)
        else:
            roots.append(node)
    return roots


def count_employees(db: Session) -> int:
    return db.scalar(select(func.count(Employee.id))) or 0
