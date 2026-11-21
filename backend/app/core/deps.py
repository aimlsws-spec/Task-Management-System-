from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import DB
from app.core.errors import AppError, Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal, effective_permissions

_ALLOWED_WHILE_MUST_CHANGE = {
    "/api/v1/auth/me",
    "/api/v1/auth/change-password",
    "/api/v1/auth/logout",
    "/api/v1/auth/logout-all",
}


# A freshly signed-up employee may only finish onboarding (and see departments to choose from) until done.
_ALLOWED_WHILE_PENDING = _ALLOWED_WHILE_MUST_CHANGE | {"/api/v1/me/onboarding", "/api/v1/departments"}


def get_principal(request: Request, db: Session = DB) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise Unauthorized()
    payload = decode_access_token(header[7:])
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.token_version != payload.get("ver"):
        raise Unauthorized("Session is no longer valid")
    if user.must_change_password and request.url.path not in _ALLOWED_WHILE_MUST_CHANGE:
        raise AppError("PASSWORD_CHANGE_REQUIRED", "You must change your password first", 403)
    employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
    if employee is not None and employee.status == "pending_setup" and request.url.path not in _ALLOWED_WHILE_PENDING:
        raise AppError("ONBOARDING_REQUIRED", "Choose your department and designation to continue", 403)
    perms, roles, rank = effective_permissions(db, user.id)
    return Principal(db=db, user=user, employee=employee, permissions=perms, roles=roles, rank=rank)


def require(*codes: str) -> Callable[..., Principal]:
    """Dependency: caller must hold ALL given permissions (at any scope). Object/scope checks follow in services."""

    def dep(request: Request, p: Principal = Depends(get_principal)) -> Principal:
        missing = [c for c in codes if not p.has(c)]
        if missing:
            audit.log(p.db, p.user.id, "AUTHZ_DENIED", "permission", ",".join(missing), request=request)
            p.db.commit()  # keep the denial record although we raise
            raise Forbidden()
        return p

    return dep
