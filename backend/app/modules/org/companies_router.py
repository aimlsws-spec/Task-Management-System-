from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select

from app.core import clock
from app.core.deps import get_principal, require
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.schemas import Strict
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.notifications import direct
from app.modules.org import invites
from app.modules.org.models import Company, CompanyCEO, Department, Employee
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.policy import Principal

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyIn(Strict):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    logo_url: str | None = None
    ceo_email: str | None = None
    ceo_user_id: int | None = None


class CompanyPatch(Strict):
    name: str | None = Field(None, min_length=2, max_length=150)
    code: str | None = Field(None, min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    logo_url: str | None = None
    is_active: bool | None = None


class AssignCEOIn(Strict):
    user_id: int | None = None
    email: str | None = None


def _company_dict(db, c: Company) -> dict:
    ceos = []
    rows = db.execute(
        select(CompanyCEO.user_id, CompanyCEO.granted_at, User.email, Employee.full_name)
        .join(User, User.id == CompanyCEO.user_id)
        .outerjoin(Employee, Employee.user_id == User.id)
        .where(CompanyCEO.company_id == c.id)
    ).all()
    for r in rows:
        ceos.append({
            "user_id": r.user_id,
            "email": r.email,
            "full_name": r.full_name or r.email,
            "granted_at": r.granted_at.isoformat() + "Z" if r.granted_at else None,
        })
    return {
        "id": c.id,
        "name": c.name,
        "code": c.code,
        "logo_url": c.logo_url,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
        "ceos": ceos,
    }


@router.get("")
def list_companies(p: Principal = Depends(get_principal)):
    q = select(Company).order_by(Company.name)
    cids = p.company_ids()
    if cids is not None:
        q = q.where(Company.id.in_(cids))
    rows = p.db.scalars(q).all()
    return [_company_dict(p.db, c) for c in rows]


@router.post("", status_code=201)
def create_company(body: CompanyIn, request: Request, p: Principal = Depends(require("employee.manage"))):
    if p.rank < 110:  # Admin or Owner
        raise Forbidden("Only the Owner or Admin can create companies")
    code = body.code.strip().lower()
    if p.db.scalar(select(Company.id).where(Company.code == code)):
        raise Conflict("COMPANY_EXISTS", f"A company with code '{code}' already exists")
    c = Company(name=body.name.strip(), code=code, logo_url=body.logo_url)
    p.db.add(c)
    p.db.flush()

    # Create default general department for the new company
    dept_code = f"GEN-{c.id}"
    if not p.db.scalar(select(Department.id).where(Department.code == dept_code)):
        p.db.add(Department(name=f"{c.name} General", code=dept_code, company_id=c.id, self_service=True))
        p.db.flush()

    # Appoint CEO upon company creation if provided
    if body.ceo_user_id is not None:
        ceo_user = p.db.get(User, body.ceo_user_id)
        if ceo_user:
            p.db.add(CompanyCEO(company_id=c.id, user_id=ceo_user.id, granted_by_user_id=p.user.id))
            ceo_role = p.db.scalar(select(Role).where(Role.code == "ceo"))
            if ceo_role and not p.db.scalar(select(UserRole.user_id).where(UserRole.user_id == ceo_user.id, UserRole.role_id == ceo_role.id)):
                p.db.add(UserRole(user_id=ceo_user.id, role_id=ceo_role.id, granted_by=p.user.id))
            p.db.flush()
            direct.invitation(p.db, "CEO", ceo_user.email, has_account=True, user_id=ceo_user.id)
    elif body.ceo_email and body.ceo_email.strip():
        ceo_email = body.ceo_email.strip().lower()
        existing_user = p.db.scalar(select(User).where(User.email == ceo_email))
        if existing_user:
            p.db.add(CompanyCEO(company_id=c.id, user_id=existing_user.id, granted_by_user_id=p.user.id))
            ceo_role = p.db.scalar(select(Role).where(Role.code == "ceo"))
            if ceo_role and not p.db.scalar(select(UserRole.user_id).where(UserRole.user_id == existing_user.id, UserRole.role_id == ceo_role.id)):
                p.db.add(UserRole(user_id=existing_user.id, role_id=ceo_role.id, granted_by=p.user.id))
            p.db.flush()
            direct.invitation(p.db, "CEO", existing_user.email, has_account=True, user_id=existing_user.id)
        else:
            invites.create_invite(p.db, p, ceo_email, "ceo", request, company_id=c.id)

    audit.log(p.db, p.user.id, "COMPANY_CREATED", "company", c.id, after={"name": c.name, "code": c.code}, request=request)
    return _company_dict(p.db, c)


@router.get("/{company_id}")
def get_company(company_id: int, p: Principal = Depends(get_principal)):
    if not p.can_access_company(company_id):
        raise NotFound("Company")
    c = p.db.get(Company, company_id)
    if not c:
        raise NotFound("Company")
    return _company_dict(p.db, c)


@router.patch("/{company_id}")
def patch_company(company_id: int, body: CompanyPatch, request: Request, p: Principal = Depends(require("employee.manage"))):
    if p.rank < 110:
        raise Forbidden("Only the Owner or Admin can update companies")
    c = p.db.get(Company, company_id)
    if not c:
        raise NotFound("Company")
    data = body.model_dump(exclude_unset=True)
    if "code" in data and data["code"]:
        data["code"] = data["code"].strip().lower()
        existing = p.db.scalar(select(Company.id).where(Company.code == data["code"], Company.id != company_id))
        if existing:
            raise Conflict("COMPANY_EXISTS", f"A company with code '{data['code']}' already exists")
    before = {k: getattr(c, k) for k in data}
    for k, v in data.items():
        setattr(c, k, v)
    audit.log(p.db, p.user.id, "COMPANY_UPDATED", "company", c.id, before=before, after=data, request=request)
    return _company_dict(p.db, c)


@router.get("/{company_id}/ceos")
def list_company_ceos(company_id: int, p: Principal = Depends(get_principal)):
    if not p.can_access_company(company_id):
        raise NotFound("Company")
    c = p.db.get(Company, company_id)
    if not c:
        raise NotFound("Company")
    return _company_dict(p.db, c)["ceos"]


@router.post("/{company_id}/ceos", status_code=201)
def assign_company_ceo(company_id: int, body: AssignCEOIn, request: Request, p: Principal = Depends(require("employee.manage"))):
    if p.rank < 110:
        raise Forbidden("Only the Owner or Admin can authorize CEOs for companies")
    c = p.db.get(Company, company_id)
    if not c:
        raise NotFound("Company")
    user_id = body.user_id
    if user_id is None and body.email:
        email_clean = body.email.strip().lower()
        u = p.db.scalar(select(User).where(User.email == email_clean))
        if not u:
            # User doesn't exist yet: create role invitation for CEO with account activation link
            invites.create_invite(p.db, p, email_clean, "ceo", request, company_id=company_id)
            return _company_dict(p.db, c)
        user_id = u.id
    if user_id is None:
        raise AppError("USER_REQUIRED", "User ID or email is required", 422)

    existing = p.db.scalar(select(CompanyCEO.company_id).where(CompanyCEO.company_id == company_id, CompanyCEO.user_id == user_id))
    if existing:
        return _company_dict(p.db, c)

    link = CompanyCEO(company_id=company_id, user_id=user_id, granted_by_user_id=p.user.id, granted_at=clock.utcnow())
    p.db.add(link)
    p.db.flush()
    audit.log(p.db, p.user.id, "COMPANY_CEO_ASSIGNED", "company", c.id, after={"company_id": company_id, "user_id": user_id}, request=request)
    return _company_dict(p.db, c)


@router.delete("/{company_id}/ceos/{user_id}", status_code=204)
def revoke_company_ceo(company_id: int, user_id: int, request: Request, p: Principal = Depends(require("employee.manage"))):
    if p.rank < 110:
        raise Forbidden("Only the Owner or Admin can revoke CEO company authorizations")
    c = p.db.get(Company, company_id)
    if not c:
        raise NotFound("Company")
    p.db.query(CompanyCEO).filter(CompanyCEO.company_id == company_id, CompanyCEO.user_id == user_id).delete()
    audit.log(p.db, p.user.id, "COMPANY_CEO_REVOKED", "company", c.id, before={"company_id": company_id, "user_id": user_id}, request=request)
