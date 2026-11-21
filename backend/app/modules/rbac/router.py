from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select

from app.core.deps import require
from app.core.errors import AppError, Forbidden, NotFound
from app.core.schemas import Strict
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.auth.service import revoke_all_sessions
from app.modules.rbac.models import SCOPES, Permission, Role, RolePermission, UserRole
from app.modules.rbac.policy import Principal, user_max_rank

router = APIRouter(tags=["roles"])


class GrantIn(Strict):
    permission: str
    scope: str


class RolePermsIn(Strict):
    grants: list[GrantIn]


class UserRolesIn(Strict):
    role_codes: list[str] = Field(min_length=1)


def _role_dict(p: Principal, r: Role) -> dict:
    rows = p.db.execute(
        select(Permission.code, RolePermission.scope)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == r.id)
        .order_by(Permission.code)
    ).all()
    return {"id": r.id, "code": r.code, "name": r.name, "rank": r.rank, "is_system": r.is_system,
            "permissions": {c: s for c, s in rows}}  # fmt: skip


@router.get("/permissions")
def list_permissions(p: Principal = Depends(require("role.manage"))):
    return [{"code": x.code, "category": x.category, "description": x.description}
            for x in p.db.scalars(select(Permission).order_by(Permission.category, Permission.code))]  # fmt: skip


@router.get("/roles")
def list_roles(p: Principal = Depends(require("role.manage"))):
    return [_role_dict(p, r) for r in p.db.scalars(select(Role).order_by(Role.rank.desc()))]


@router.put("/roles/{role_id}/permissions")
def set_role_permissions(role_id: int, body: RolePermsIn, request: Request, p: Principal = Depends(require("role.manage"))):
    role = p.db.get(Role, role_id)
    if role is None:
        raise NotFound("Role")
    if role.rank > p.rank:
        raise Forbidden("You cannot edit a role above your own rank")
    perms = {x.code: x for x in p.db.scalars(select(Permission))}
    for g in body.grants:
        if g.permission not in perms:
            raise AppError("UNKNOWN_PERMISSION", f"Unknown permission {g.permission}", 422)
        if g.scope not in SCOPES:
            raise AppError("UNKNOWN_SCOPE", f"Unknown scope {g.scope}", 422)
    before = _role_dict(p, role)["permissions"]
    p.db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    for g in body.grants:
        p.db.add(RolePermission(role_id=role.id, permission_id=perms[g.permission].id, scope=g.scope))
    p.db.flush()
    after = _role_dict(p, role)["permissions"]
    audit.log(p.db, p.user.id, "ROLE_PERMISSIONS_CHANGED", "role", role.id, before=before, after=after, request=request)
    return _role_dict(p, role)


@router.put("/users/{user_id}/roles")
def set_user_roles(user_id: int, body: UserRolesIn, request: Request, p: Principal = Depends(require("role.manage"))):
    user = p.db.get(User, user_id)
    if user is None:
        raise NotFound("User")
    if user_max_rank(p.db, user.id) > p.rank:
        raise Forbidden("You cannot change roles of a user who outranks you")
    roles = p.db.scalars(select(Role).where(Role.code.in_(body.role_codes))).all()
    if len(roles) != len(set(body.role_codes)):
        raise AppError("UNKNOWN_ROLE", "One or more roles do not exist", 422)
    if any(r.rank > p.rank for r in roles):
        raise Forbidden("You cannot grant a role above your own rank")
    before = [r for r in p.db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id))]
    p.db.query(UserRole).filter(UserRole.user_id == user.id).delete()
    for r in roles:
        p.db.add(UserRole(user_id=user.id, role_id=r.id, granted_by=p.user.id))
    p.db.flush()
    revoke_all_sessions(p.db, user)  # force re-login so new permissions apply at once
    if sorted(before) != sorted(body.role_codes):
        from app.modules.notifications import direct

        direct.role_changed(p.db, user.email, user.id, [r.name for r in sorted(roles, key=lambda r: -r.rank)])
    audit.log(p.db, p.user.id, "USER_ROLES_CHANGED", "user", user.id, before={"roles": sorted(before)},
              after={"roles": sorted(body.role_codes)}, request=request)  # fmt: skip
    return {"user_id": user.id, "roles": sorted(body.role_codes)}
