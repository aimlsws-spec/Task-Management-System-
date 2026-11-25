from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import EmailStr, Field
from sqlalchemy import select

from app.core.deps import get_principal, require
from app.core.errors import Forbidden, NotFound
from app.core.schemas import Strict
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.auth.service import revoke_all_sessions
from app.modules.notifications import direct
from app.modules.org import admin_service, invites, service
from app.modules.org import models as org_models
from app.modules.org.admin_service import UNASSIGNED_CODE
from app.modules.org.models import Company, Department, Employee, ReportingRelationship
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
    company_id: int | None = None


class DepartmentPatch(Strict):
    name: str | None = Field(None, min_length=2, max_length=100)
    company_id: int | None = None
    is_active: bool | None = None
    self_service: bool | None = None  # selectable by new employees at sign-up


class HeadIn(Strict):
    head_employee_id: int | None
    regroup_members: bool = False  # move the department's members under this head


class SubHeadIn(Strict):
    sub_head_employee_id: int | None


class OnboardingIn(Strict):
    department_id: int
    designation: str = Field(min_length=2, max_length=100)


class DepartmentLeadersIn(Strict):
    head_employee_ids: list[int] = Field(default_factory=list)
    sub_head_employee_ids: list[int] = Field(default_factory=list)


class CompaniesIn(Strict):
    company_ids: list[int] = Field(default_factory=list)


def _dept(db, d: Department) -> dict:
    leaders = org_models.department_leaders(db, d.id)
    c_ids = org_models.department_company_ids(db, d)
    return {
        "id": d.id, "name": d.name, "code": d.code, "parent_id": d.parent_id,
        "company_id": getattr(d, "company_id", 1),
        "head_employee_id": d.head_employee_id,
        "sub_head_employee_id": getattr(d, "sub_head_employee_id", None),
        "head_employee_ids": leaders["heads"],
        "sub_head_employee_ids": leaders["sub_heads"],
        "company_ids": sorted(c_ids) if c_ids is not None else [],
        "is_shared": d.company_id is None,
        "qa_employee_id": d.qa_employee_id, "is_active": d.is_active,
        "is_system": d.is_system, "self_service": d.self_service,
    }


@router.get("/departments")
def list_departments(company_id: int | None = None, p: Principal = Depends(get_principal)):
    # Department names are not sensitive and every user needs them for pickers/filters.
    q = select(Department).order_by(Department.name)
    cids = p.company_ids()
    if cids is not None:
        if company_id is not None and company_id not in cids:
            return []
        from app.modules.org.models import DepartmentCompany
        dept_ids_in_allowed = select(DepartmentCompany.department_id).where(DepartmentCompany.company_id.in_(cids))
        q = q.where((Department.company_id.in_(cids)) | (Department.id.in_(dept_ids_in_allowed)) | (Department.company_id.is_(None)))
    elif company_id is not None:
        from app.modules.org.models import DepartmentCompany
        dept_ids_in_co = select(DepartmentCompany.department_id).where(DepartmentCompany.company_id == company_id)
        q = q.where((Department.company_id == company_id) | (Department.id.in_(dept_ids_in_co)) | (Department.company_id.is_(None)))
    return [_dept(p.db, d) for d in p.db.scalars(q)]


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, request: Request, p: Principal = Depends(require("department.manage"))):
    cid = body.company_id
    if cid is None:
        cids = p.company_ids()
        if cids is not None:
            cid = next(iter(cids)) if cids else 1
        else:
            cid = 1
    return _dept(p.db, service.create_department(p.db, p, body.name, body.code, body.parent_id, request, company_id=cid))


@router.patch("/departments/{dept_id}")
def update_department(dept_id: int, body: DepartmentPatch, request: Request, p: Principal = Depends(require("department.manage"))):
    d = _or_404(p.db.get(Department, dept_id), "Department")
    if not p.can_access_company(getattr(d, "company_id", 1)):
        raise Forbidden("You cannot manage departments for this company")
    data = body.model_dump(exclude_unset=True)
    before = {k: getattr(d, k) for k in data}
    for k, v in data.items():
        setattr(d, k, v)
    audit.log(p.db, p.user.id, "DEPARTMENT_UPDATED", "department", d.id, before=before, after=data, request=request)
    return _dept(p.db, d)


@router.put("/departments/{dept_id}/head")
def set_head(dept_id: int, body: HeadIn, request: Request, p: Principal = Depends(require("department.manage"))):
    d = _or_404(p.db.get(Department, dept_id), "Department")
    if not p.can_access_company(getattr(d, "company_id", 1)):
        raise Forbidden("You cannot manage departments for this company")
    moved = service.set_department_head(p.db, p, d, body.head_employee_id, request, regroup=body.regroup_members)
    return {**_dept(p.db, d), "members_moved": moved}


@router.put("/departments/{dept_id}/subhead")
def set_subhead(dept_id: int, body: SubHeadIn, request: Request, p: Principal = Depends(require("department.manage"))):
    d = _or_404(p.db.get(Department, dept_id), "Department")
    if not p.can_access_company(getattr(d, "company_id", 1)):
        raise Forbidden("You cannot manage departments for this company")
    service.set_department_sub_head(p.db, p, d, body.sub_head_employee_id, request)
    return _dept(p.db, d)


@router.put("/departments/{dept_id}/leaders")
def set_department_leaders(dept_id: int, body: DepartmentLeadersIn, request: Request, p: Principal = Depends(require("department.manage"))):
    d = _or_404(p.db.get(Department, dept_id), "Department")
    if not p.can_access_company(getattr(d, "company_id", 1)):
        raise Forbidden("You cannot manage departments for this company")
    service.set_department_leaders(p.db, p, d, body.head_employee_ids, body.sub_head_employee_ids, request)
    return _dept(p.db, d)


@router.put("/departments/{dept_id}/companies")
def set_department_companies(dept_id: int, body: CompaniesIn, request: Request, p: Principal = Depends(require("department.manage"))):
    d = _or_404(p.db.get(Department, dept_id), "Department")
    service.set_department_companies(p.db, p, d, body.company_ids, request)
    return _dept(p.db, d)


@router.put("/employees/{emp_id}/companies")
def set_employee_companies(emp_id: int, body: CompaniesIn, request: Request, p: Principal = Depends(require("employee.manage"))):
    emp = _or_404(p.db.get(Employee, emp_id), "Employee")
    service.set_employee_companies(p.db, p, emp, body.company_ids, request)
    return service.employee_dict(p.db, emp)


class QaIn(Strict):
    qa_employee_id: int | None


@router.put("/departments/{dept_id}/qa")
def set_qa(dept_id: int, body: QaIn, request: Request, p: Principal = Depends(require("department.manage"))):
    """ADR 008: the department's QA tester. Finished work from the department is tested by them before the head reviews it."""
    d = _or_404(p.db.get(Department, dept_id), "Department")
    service.set_department_qa(p.db, p, d, body.qa_employee_id, request)
    return _dept(p.db, d)


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
    company_id: int | None = None
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
    company_id: int | None = None
    daily_capacity_hours: float | None = Field(None, gt=0, le=16)
    can_receive_tasks: bool | None = None
    status: str | None = Field(None, pattern=r"^(active|on_leave)$")
    role_codes: list[str] | None = None


def _visible_employee(p: Principal, emp_id: int) -> Employee:
    emp = p.db.get(Employee, emp_id)
    # Out-of-scope is reported as 404 so existence is not leaked.
    if emp is None or not p.can_see("employee.view", emp.id):
        raise NotFound("Employee")
    cids = p.company_ids()
    if cids is not None:
        from app.modules.org.models import employee_company_ids
        emp_cids = employee_company_ids(p.db, emp)
        if emp_cids is not None and not any(cid in cids for cid in emp_cids):
            raise NotFound("Employee")
    return emp


@router.get("/employees")
def list_employees(
    company_id: int | None = None,
    department_id: int | None = None, status: str | None = None, q: str | None = None,
    page: int = 1, page_size: int = 50, p: Principal = Depends(require("employee.view")),
):  # fmt: skip
    page_size = max(1, min(page_size, 200))
    stmt = select(Employee)
    ids = p.scope_employee_ids("employee.view")
    if ids is not None:
        stmt = stmt.where(Employee.id.in_(ids))

    cids = p.company_ids()
    if cids is not None:
        from app.modules.org.models import EmployeeCompany
        emp_ids_in_allowed = select(EmployeeCompany.employee_id).where(EmployeeCompany.company_id.in_(cids))
        stmt = stmt.where((Employee.company_id.in_(cids)) | (Employee.id.in_(emp_ids_in_allowed)))
        if company_id is not None and company_id not in cids:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

    if company_id is not None:
        from app.modules.org.models import EmployeeCompany
        emp_ids_in_co = select(EmployeeCompany.employee_id).where(EmployeeCompany.company_id == company_id)
        stmt = stmt.where((Employee.company_id == company_id) | (Employee.id.in_(emp_ids_in_co)))

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


class ApproveIn(Strict):
    department_id: int | None = None
    job_title: str | None = None


@router.get("/employees/pending-approvals")
def list_pending_approvals(company_id: int | None = None, p: Principal = Depends(require("employee.manage"))):
    if p.rank < 90:
        raise Forbidden("Only CEO, Owner or Admin can review pending employee approvals")
    stmt = select(Employee).where(Employee.status == "pending_approval")
    cids = p.company_ids()
    if cids is not None:
        if company_id is not None and company_id not in cids:
            return []
        stmt = stmt.where(Employee.company_id.in_(cids))
    elif company_id is not None:
        stmt = stmt.where(Employee.company_id == company_id)
    rows = p.db.scalars(stmt.order_by(Employee.id.desc())).all()
    return [service.employee_dict(p.db, e) for e in rows]


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


@router.post("/employees/{emp_id}/approve")
def approve_employee(emp_id: int, request: Request, body: ApproveIn | None = None, p: Principal = Depends(require("employee.manage"))):
    if p.rank < 90:
        raise Forbidden("Only CEO, Owner or Admin can approve employee join requests")
    emp = p.db.get(Employee, emp_id)
    if emp is None or emp.status != "pending_approval":
        raise NotFound("Pending employee join request not found")
    cid = getattr(emp, "company_id", 1) or 1
    if not p.can_access_company(cid):
        raise Forbidden("You are not authorized to approve join requests for this company")

    u = p.db.get(User, emp.user_id)
    comp = p.db.get(Company, cid) if cid else None
    comp_name = comp.name if comp else "the company"

    if body and body.department_id:
        dept = p.db.get(Department, body.department_id)
        if dept and dept.is_active:
            emp.department_id = dept.id
    else:
        holding = p.db.scalar(select(Department).where(Department.code == UNASSIGNED_CODE))
        if holding and emp.department_id == holding.id:
            # assign first active department in this company
            co_dept = p.db.scalar(
                select(Department)
                .where(Department.company_id == cid, Department.is_active.is_(True), Department.id != holding.id)
                .order_by(Department.id)
                .limit(1)
            )
            if co_dept:
                emp.department_id = co_dept.id

    if body and body.job_title:
        emp.job_title = body.job_title.strip()[:100]
    elif not emp.job_title:
        emp.job_title = "Team Member"

    emp.status = "active"
    if u:
        u.is_active = True
    p.db.flush()

    dept = p.db.get(Department, emp.department_id)
    if dept:
        boss = service.default_manager_id(p.db, dept, exclude_employee_id=emp.id)
        if boss:
            try:
                service.set_manager(p.db, p, emp.id, boss, request, audit_it=False)
            except Exception:
                pass

    if u:
        direct.employee_approved(p.db, u.email, u.id, emp.full_name, comp_name)
    audit.log(p.db, p.user.id, "EMPLOYEE_APPROVED", "employee", emp.id,
              after={"company_id": cid, "department_id": emp.department_id, "status": "active"}, request=request)
    return service.employee_dict(p.db, emp)


@router.post("/employees/{emp_id}/reject")
def reject_employee(emp_id: int, request: Request, p: Principal = Depends(require("employee.manage"))):
    if p.rank < 90:
        raise Forbidden("Only CEO, Owner or Admin can reject employee join requests")
    emp = p.db.get(Employee, emp_id)
    if emp is None or emp.status != "pending_approval":
        raise NotFound("Pending employee join request not found")
    cid = getattr(emp, "company_id", 1) or 1
    if not p.can_access_company(cid):
        raise Forbidden("You are not authorized to reject join requests for this company")

    u = p.db.get(User, emp.user_id)
    comp = p.db.get(Company, cid) if cid else None
    comp_name = comp.name if comp else "the company"

    emp.status = "rejected"
    if u:
        u.is_active = False
        revoke_all_sessions(p.db, u)
    p.db.flush()

    if u:
        direct.employee_rejected(p.db, u.email, u.id, emp.full_name, comp_name)
    audit.log(p.db, p.user.id, "EMPLOYEE_REJECTED", "employee", emp.id,
              after={"company_id": cid, "status": "rejected"}, request=request)
    return {"message": "Employee join request rejected"}


# ---------------- role emails (Admin) ----------------
class RoleInviteIn(Strict):
    email: EmailStr
    role_code: str = Field(min_length=2, max_length=50)
    company_id: int | None = None


@router.get("/role-invites")
def list_role_invites(p: Principal = Depends(require("employee.manage"))):
    return invites.list_invites(p.db, p)


@router.post("/role-invites", status_code=201)
def create_role_invite(body: RoleInviteIn, request: Request, p: Principal = Depends(require("employee.manage"))):
    return invites.invite_dict(p.db, invites.create_invite(p.db, p, body.email, body.role_code, request, company_id=body.company_id))


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
def tree(company_id: int | None = None, p: Principal = Depends(require("employee.view"))):
    cids = p.company_ids()
    if cids is not None:
        if company_id is not None and company_id not in cids:
            return []
        if company_id is None and len(cids) == 1:
            company_id = next(iter(cids))
    return service.hierarchy_tree(p.db, p.scope_employee_ids("employee.view"), company_id=company_id, allowed_company_ids=cids)


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
