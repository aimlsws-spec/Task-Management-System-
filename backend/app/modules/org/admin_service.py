"""Admin-panel operations: delete departments, regroup under heads, self sign-up and first-login onboarding."""

from datetime import date

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.core.security import hash_password, validate_password_policy
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.notifications import direct, outbox
from app.modules.org import codes, invites
from app.modules.org.models import Company, CompanyCEO, Department, Employee, EmployeeCompany, ManagerDepartment
from app.modules.org.service import PENDING, current_manager_id, default_manager_id, set_manager
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.policy import Principal, user_max_rank

UNASSIGNED_CODE = "UNASSIGNED"  # holding department for people who signed up but have not finished setup


def delete_department(db: Session, p: Principal, dept: Department, request: Request) -> None:
    if dept.is_system:
        raise Conflict("SYSTEM_DEPARTMENT", "System departments cannot be deleted")
    if db.scalar(select(func.count(Employee.id)).where(Employee.department_id == dept.id)):
        raise Conflict("DEPARTMENT_NOT_EMPTY", "Move or remove its employees first (or deactivate the department instead)")
    if db.scalar(select(func.count(Department.id)).where(Department.parent_id == dept.id)):
        raise Conflict("DEPARTMENT_HAS_CHILDREN", "Delete or move its sub-departments first")
    db.query(ManagerDepartment).filter(ManagerDepartment.department_id == dept.id).delete()
    audit.log(db, p.user.id, "DEPARTMENT_DELETED", "department", dept.id,
              before={"name": dept.name, "code": dept.code}, request=request)  # fmt: skip
    db.delete(dept)


def regroup_department_under_head(db: Session, p: Principal, dept: Department, request: Request) -> int:
    """Point every active member of `dept` (except the head and anyone outranking the head) at the head."""
    head = db.get(Employee, dept.head_employee_id) if dept.head_employee_id else None
    if head is None:
        return 0
    head_rank = user_max_rank(db, head.user_id)
    moved = 0
    members = db.scalars(
        select(Employee).where(Employee.department_id == dept.id, Employee.status != "inactive", Employee.id != head.id)
    ).all()
    for emp in members:
        if user_max_rank(db, emp.user_id) > head_rank or current_manager_id(db, emp.id) == head.id:
            continue
        try:
            set_manager(db, p, emp.id, head.id, request, audit_it=False)
            moved += 1
        except AppError:  # e.g. would create a cycle: leave that person where they are
            continue
    if current_manager_id(db, head.id) is None:  # a head with nobody above them reports to the Manager
        mgr = default_manager_id(db, dept, exclude_employee_id=head.id)
        if mgr is not None:
            set_manager(db, p, head.id, mgr, request, audit_it=False)
    audit.log(db, p.user.id, "DEPARTMENT_REGROUPED", "department", dept.id,
              after={"head_employee_id": head.id, "moved": moved}, request=request)  # fmt: skip
    return moved


def signup(
    db: Session,
    full_name: str,
    email: str,
    password: str,
    request: Request | None,
    company_id: int | None = None,
    department_id: int | None = None,
) -> Employee:
    email = email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("EMAIL_EXISTS", "An account with this email already exists. Try signing in.")
    validate_password_policy(password)
    holding = db.scalar(select(Department).where(Department.code == UNASSIGNED_CODE))
    role = db.scalar(select(Role).where(Role.code == "employee"))
    if holding is None or role is None:
        raise AppError("SETUP_INCOMPLETE", "Organization is not set up yet. Contact your administrator.", 503)
    user = User(email=email, password_hash=hash_password(password), must_change_password=False)
    db.add(user)
    db.flush()
    emp = Employee(user_id=user.id, employee_code=codes.generate(db), full_name=full_name, department_id=holding.id,
                   status=PENDING, joined_on=date.today())  # fmt: skip
    db.add(emp)
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()

    inv = invites.find_unclaimed(db, email)
    if inv is not None:  # the Admin / CEO registered this email for a role (ADR 002)
        invites.apply_at_signup(db, inv, user, emp, request)
        names = list(db.scalars(select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)))
        role_title = ", ".join(names) or "Employee"
        needs_onboarding = emp.status == PENDING
        direct.welcome(db, email, user.id, full_name, role_title, needs_onboarding=needs_onboarding)
        audit.log(db, user.id, "SIGNUP", "employee", emp.id, after={"email": email, "role": role_title}, request=request)
        outbox.emit(db, "EMPLOYEE_SIGNED_UP", None, user.id, {"after": {"name": full_name, "email": email, "role": role_title, "needs_onboarding": needs_onboarding}})
        return emp

    # Self sign-up: requires selecting a company and getting leadership (Owner / CEO) approval
    if company_id is None:
        active_companies = db.scalars(select(Company).where(Company.is_active.is_(True))).all()
        if len(active_companies) == 1:
            comp = active_companies[0]
        else:
            raise AppError("COMPANY_REQUIRED", "Please select a company to join", 422)
    else:
        comp = db.get(Company, company_id)
        if comp is None or not comp.is_active:
            raise AppError("INVALID_COMPANY", "Selected company not found or inactive", 422)

    dept = None
    if department_id is not None:
        dept = db.get(Department, department_id)
        if dept is None or not dept.is_active or dept.is_system:
            raise AppError("INVALID_DEPARTMENT", "Selected department not found or inactive", 422)
        if dept.company_id is not None and dept.company_id != comp.id:
            raise AppError("INVALID_DEPARTMENT", "Selected department does not belong to this company", 422)
    else:
        available_depts = db.scalars(
            select(Department)
            .where(
                (Department.company_id == comp.id) | (Department.company_id.is_(None)),
                Department.is_active.is_(True),
                Department.is_system.is_(False),
            )
            .order_by(Department.id)
        ).all()
        if available_depts:
            dept = available_depts[0]

    emp.company_id = comp.id
    if dept is not None:
        emp.department_id = dept.id
    emp.status = "pending_approval"
    db.add(EmployeeCompany(employee_id=emp.id, company_id=comp.id))
    db.flush()

    # Emit outbox notification for Owner and specific Company CEO
    payload = {
        "after": {
            "name": full_name,
            "email": email,
            "company_id": comp.id,
            "company_name": comp.name,
            "department_id": dept.id if dept else None,
            "department_name": dept.name if dept else None,
            "user_id": user.id,
            "employee_id": emp.id,
        }
    }
    outbox.emit(db, "EMPLOYEE_JOIN_REQUEST", None, user.id, payload)

    # Direct email to Owner(s) and this specific company's CEO(s)
    owners = db.execute(
        select(User.id, User.email)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code.in_(["owner", "admin"]), User.is_active.is_(True))
    ).all()
    ceos = db.execute(
        select(User.id, User.email)
        .join(CompanyCEO, CompanyCEO.user_id == User.id)
        .where(CompanyCEO.company_id == comp.id, User.is_active.is_(True))
    ).all()
    notified = set()
    dept_name = dept.name if dept else None
    for u_id, u_email in list(owners) + list(ceos):
        if u_email not in notified:
            notified.add(u_email)
            direct.join_request(db, u_email, u_id, full_name, email, comp.name, dept_name)

    direct.join_request_submitted(db, email, user.id, full_name, comp.name, dept_name)
    audit.log(
        db,
        user.id,
        "EMPLOYEE_JOIN_REQUESTED",
        "employee",
        emp.id,
        after={
            "email": email,
            "company_id": comp.id,
            "company_name": comp.name,
            "department_id": dept.id if dept else None,
            "department_name": dept_name,
        },
        request=request,
    )
    return emp


def complete_onboarding(db: Session, p: Principal, department_id: int, designation: str, request: Request | None) -> dict:
    emp = p.employee
    if emp is None or emp.status != PENDING:
        raise Conflict("ALREADY_ONBOARDED", "Your profile is already set up")
    dept = db.get(Department, department_id)
    if dept is None or not dept.is_active or dept.is_system or not dept.self_service:
        raise AppError("INVALID_DEPARTMENT", "Please choose one of the listed departments", 422)
    title = designation.strip()
    if len(title) < 2:
        raise AppError("INVALID_DESIGNATION", "Please enter your designation", 422)
    emp.department_id, emp.job_title, emp.status = dept.id, title[:100], "active"
    boss = default_manager_id(db, dept, exclude_employee_id=emp.id)
    set_manager(db, p, emp.id, boss, request, audit_it=False)
    audit.log(db, p.user.id, "ONBOARDING_COMPLETED", "employee", emp.id,
              after={"department_id": dept.id, "designation": emp.job_title, "reports_to_id": boss}, request=request)  # fmt: skip
    return {"department_id": dept.id, "designation": emp.job_title, "reports_to_id": boss}
