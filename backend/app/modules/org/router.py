from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import EmailStr, Field
from sqlalchemy import select

from app.core.deps import get_principal, require
from app.core.errors import NotFound
from app.core.schemas import Strict
from app.modules.audit import service as audit
from app.modules.org import admin_service, invites, service
from app.modules.org.models import Department, Employee, ReportingRelationship
from app.modules.rbac.policy import Principal

router = APIRouter(tags=["organization"])


def _or_404(obj, what: str):
    if obj is None:
        raise NotFound(what)
    return obj


# ---------------- departments ----------------
class DepartmentIn(Strict):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    parent_id: int | None = None


class DepartmentPatch(Strict):
    name: str | None = Field(None, min_length=2, max_length=100)
    is_active: bool | None = None
    self_service: bool | None = None  # selectable by new employees at sign-up


class HeadIn(Strict):
    head_employee_id: int | None
    regroup_members: bool = False  # move the department's members under this head


class OnboardingIn(Strict):
    department_id: int
    designation: str = Field(min_length=2, max_length=100)


def _dept(d: Department) -> dict:
    return {"id": d.id, "name": d.name, "code": d.code, "parent_id": d.parent_id,
            "head_employee_id": d.head_employee_id, "qa_employee_id": d.qa_employee_id, "is_active": d.is_active,
            "is_system": d.is_system, "self_service": d.self_service}  # fmt: skip


@router.get("/departments")
def list_departments(p: Principal = Depends(get_principal)):
    # Department names are not sensitive and every user needs them for pickers/filters.
    return [_dept(d) for d in p.db.scalars(select(Department).order_by(Department.name))]


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, request: Request, p: Principal = Depends(require("department.manage"))):
    return _dept(service.create_department(p.db, p, body.name, body.code, body.parent_id, request))


@router.patch("/departments/{dept_id}")
def update_department(dept_id: int, body: DepartmentPatch, request: Request, p: Principal = Depends(require("department.manage"))):
    d = _or_404(p.db.get(Department, dept_id), "Department")
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(d, k) for k in data}
    for k, v in data.items():
        setattr(d, k, v)
    audit.log(p.db, p.user.id, "DEPARTMENT_UPDATED", "department", d.id, before=before, after=data, request=request)
    return _dept(d)


@router.put("/departments/{dept_id}/head")
def set_head(dept_id: int, body: HeadIn, request: Request, p: Principal = Depends(require("department.manage"))):
    d = _or_404(p.db.get(Department, dept_id), "Department")
    moved = service.set_department_head(p.db, p, d, body.head_employee_id, request, regroup=body.regroup_members)
    return {**_dept(d), "members_moved": moved}


class QaIn(Strict):
    qa_employee_id: int | None


@router.put("/departments/{dept_id}/qa")
def set_qa(dept_id: int, body: QaIn, request: Request, p: Principal = Depends(require("department.manage"))):
    """ADR 008: the department's QA tester. Finished work from the department is tested by them before the head reviews it."""
    d = _or_404(p.db.get(Department, dept_id), "Department")
    service.set_department_qa(p.db, p, d, body.qa_employee_id, request)
    return _dept(d)


@router.delete("/departments/{dept_id}", status_code=204)
def delete_department(dept_id: int, request: Request, p: Principal = Depends(require("department.manage"))):
    admin_service.delete_department(p.db, p, _or_404(p.db.get(Department, dept_id), "Department"), request)


@router.post("/me/onboarding")
def onboarding(body: OnboardingIn, request: Request, p: Principal = Depends(get_principal)):
    """First login after self sign-up: choose department + designation; placed under that department's head."""
    return admin_service.complete_onboarding(p.db, p, body.department_id, body.designation, request)


# ---------------- employees ----------------
class EmployeeIn(Strict):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    employee_code: str | None = Field(None, max_length=30)  # empty = a unique letters+digits ID is generated (ADR 008)
    department_id: int
    job_title: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=30)
    joined_on: date | None = None
    temp_password: str = Field(max_length=200)
    role_codes: list[str] = Field(default_factory=lambda: ["employee"])
    reports_to_id: int | None = None


class EmployeePatch(Strict):
    full_name: str | None = Field(None, min_length=2, max_length=150)
    job_title: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=30)
    department_id: int | None = None
    daily_capacity_hours: float | None = Field(None, gt=0, le=16)
    can_receive_tasks: bool | None = None
    status: str | None = Field(None, pattern=r"^(active|on_leave)$")
    role_codes: list[str] | None = None


def _visible_employee(p: Principal, emp_id: int) -> Employee:
    emp = p.db.get(Employee, emp_id)
    # Out-of-scope is reported as 404 so existence is not leaked.
    if emp is None or not p.can_see("employee.view", emp.id):
        raise NotFound("Employee")
    return emp


@router.get("/employees")
def list_employees(
    department_id: int | None = None, status: str | None = None, q: str | None = None,
    page: int = 1, page_size: int = 50, p: Principal = Depends(require("employee.view")),
):  # fmt: skip
    page_size = max(1, min(page_size, 200))
    stmt = select(Employee)
    ids = p.scope_employee_ids("employee.view")
    if ids is not None:
        stmt = stmt.where(Employee.id.in_(ids))
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if status:
        stmt = stmt.where(Employee.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Employee.full_name.like(like) | Employee.employee_code.like(like))
    from sqlalchemy import func

    total = p.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = p.db.scalars(stmt.order_by(Employee.full_name).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [service.employee_dict(p.db, e) for e in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/employees", status_code=201)
def create_employee(body: EmployeeIn, request: Request, p: Principal = Depends(require("employee.manage"))):
    emp = service.create_employee(p.db, p, body.model_dump(), request)
    return service.employee_dict(p.db, emp)


@router.get("/employees/{emp_id}")
def get_employee(emp_id: int, p: Principal = Depends(require("employee.view"))):
    return service.employee_dict(p.db, _visible_employee(p, emp_id))


@router.patch("/employees/{emp_id}")
def patch_employee(emp_id: int, body: EmployeePatch, request: Request, p: Principal = Depends(require("employee.manage"))):
    emp = _or_404(p.db.get(Employee, emp_id), "Employee")
    service.update_employee(p.db, p, emp, body.model_dump(exclude_unset=True), request)
    return service.employee_dict(p.db, emp)


@router.post("/employees/{emp_id}/deactivate")
def deactivate(emp_id: int, request: Request, p: Principal = Depends(require("employee.manage"))):
    emp = _or_404(p.db.get(Employee, emp_id), "Employee")
    return service.deactivate_employee(p.db, p, emp, request)


@router.post("/employees/{emp_id}/reactivate")
def reactivate(emp_id: int, request: Request, p: Principal = Depends(require("employee.manage"))):
    emp = _or_404(p.db.get(Employee, emp_id), "Employee")
    service.reactivate_employee(p.db, p, emp, request)
    return service.employee_dict(p.db, emp)


# ---------------- role emails (Admin) ----------------
class RoleInviteIn(Strict):
    email: EmailStr
    role_code: str = Field(min_length=2, max_length=50)


@router.get("/role-invites")
def list_role_invites(p: Principal = Depends(require("employee.manage"))):
    return invites.list_invites(p.db)


@router.post("/role-invites", status_code=201)
def create_role_invite(body: RoleInviteIn, request: Request, p: Principal = Depends(require("employee.manage"))):
    return invites.invite_dict(p.db, invites.create_invite(p.db, p, body.email, body.role_code, request))


@router.post("/role-invites/{invite_id}/resend")
def resend_role_invite(invite_id: int, request: Request, p: Principal = Depends(require("employee.manage"))):
    return invites.invite_dict(p.db, invites.resend_invite(p.db, p, invite_id, request))


@router.delete("/role-invites/{invite_id}", status_code=204)
def revoke_role_invite(invite_id: int, request: Request, p: Principal = Depends(require("employee.manage"))):
    invites.revoke_invite(p.db, p, invite_id, request)


# ---------------- hierarchy ----------------
class ManagerIn(Strict):
    employee_id: int
    reports_to_id: int | None


@router.get("/hierarchy/tree")
def tree(p: Principal = Depends(require("employee.view"))):
    return service.hierarchy_tree(p.db, p.scope_employee_ids("employee.view"))


@router.get("/hierarchy/relationships")
def relationships(employee_id: int, p: Principal = Depends(require("employee.view"))):
    _visible_employee(p, employee_id)
    rows = p.db.scalars(
        select(ReportingRelationship).where(ReportingRelationship.employee_id == employee_id).order_by(ReportingRelationship.effective_from)
    )
    return [
        {"id": r.id, "reports_to_id": r.reports_to_id, "relation_type": r.relation_type,
         "effective_from": r.effective_from.isoformat() + "Z",
         "effective_to": r.effective_to.isoformat() + "Z" if r.effective_to else None}
        for r in rows
    ]  # fmt: skip


@router.post("/hierarchy/relationships", status_code=204)
def change_manager(body: ManagerIn, request: Request, p: Principal = Depends(require("hierarchy.manage"))):
    service.set_manager(p.db, p, body.employee_id, body.reports_to_id, request)
