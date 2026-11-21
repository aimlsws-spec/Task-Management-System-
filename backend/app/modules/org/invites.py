"""Admin-registered role emails (ADR 002). Whoever signs up with a registered email receives that role."""

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.audit import service as audit
from app.modules.auth.models import User
from app.modules.auth.service import revoke_all_sessions
from app.modules.notifications import direct
from app.modules.org.models import Department, Employee, RoleInvite
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.policy import Principal

MGMT_CODE = "MGMT"
# Roles whose holders belong to Management and skip the department/designation onboarding.
MANAGEMENT_ROLES = {"owner": "Owner", "ceo": "CEO", "manager": "Manager"}
# Who a newly invited management person reports to: the first active holder of one of these roles.
BOSS_ROLES = {"ceo": ["owner"], "manager": ["ceo", "owner"]}


def norm(email: str) -> str:
    return email.strip().lower()


def invite_dict(db: Session, i: RoleInvite) -> dict:
    role = db.get(Role, i.role_id)
    return {
        "id": i.id, "email": i.email, "role_code": role.code, "role_name": role.name,
        "claimed": i.claimed_at is not None,
        "claimed_at": i.claimed_at.isoformat() + "Z" if i.claimed_at else None,
        "created_at": i.created_at.isoformat() + "Z",
    }  # fmt: skip


def list_invites(db: Session) -> list[dict]:
    return [invite_dict(db, i) for i in db.scalars(select(RoleInvite).order_by(RoleInvite.id.desc()))]


def create_invite(db: Session, p: Principal, email: str, role_code: str, request: Request) -> RoleInvite:
    email = norm(email)
    role = db.scalar(select(Role).where(Role.code == role_code))
    if role is None or role.code == "admin":  # Admin accounts are only ever created by bootstrap-admin
        raise AppError("INVALID_ROLE", "Choose Owner, CEO, Manager, Department Head or Employee", 422)
    if role.rank > p.rank:
        raise Forbidden("You cannot grant a role above your own rank")
    if db.scalar(select(RoleInvite.id).where(RoleInvite.email == email)):
        raise Conflict("INVITE_EXISTS", "This email already has a role registered")
    inv = RoleInvite(email=email, role_id=role.id, created_by=p.user.id)
    db.add(inv)
    db.flush()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:  # they signed up before the Admin registered them: grant now, applies at next login
        if not db.scalar(select(UserRole.user_id).where(UserRole.user_id == user.id, UserRole.role_id == role.id)):
            db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=p.user.id))
        inv.claimed_user_id, inv.claimed_at = user.id, clock.utcnow()
        db.flush()
        revoke_all_sessions(db, user)
    _send_invitation(db, role, email, has_account=user is not None, user_id=user.id if user else None)
    audit.log(db, p.user.id, "ROLE_INVITE_CREATED", "role_invite", inv.id,
              after={"email": email, "role": role.code, "applied_to_existing_user": user is not None}, request=request)  # fmt: skip
    return inv


def _send_invitation(db: Session, role: Role, email: str, has_account: bool, user_id: int | None) -> None:
    direct.invitation(db, role.name, email, has_account, user_id)


def resend_invite(db: Session, p: Principal, invite_id: int, request: Request) -> RoleInvite:
    """Send the invitation again (it may have landed in spam). Only while the person has not signed up."""
    inv = db.get(RoleInvite, invite_id)
    if inv is None:
        raise NotFound("Role email")
    if inv.claimed_at is not None:
        raise Conflict("INVITE_CLAIMED", "This person has already signed up")
    _send_invitation(db, db.get(Role, inv.role_id), inv.email, has_account=False, user_id=None)
    audit.log(db, p.user.id, "ROLE_INVITE_RESENT", "role_invite", inv.id, after={"email": inv.email}, request=request)
    return inv


def revoke_invite(db: Session, p: Principal, invite_id: int, request: Request) -> None:
    inv = db.get(RoleInvite, invite_id)
    if inv is None:
        raise NotFound("Role email")
    if inv.claimed_at is not None:
        raise Conflict("INVITE_CLAIMED", "This email has already signed up. Change the person's role under Employees.")
    audit.log(db, p.user.id, "ROLE_INVITE_REVOKED", "role_invite", inv.id, before={"email": inv.email}, request=request)
    db.delete(inv)


def find_unclaimed(db: Session, email: str) -> RoleInvite | None:
    return db.scalar(select(RoleInvite).where(RoleInvite.email == norm(email), RoleInvite.claimed_at.is_(None)))


class _System:
    """Stand-in principal for the sign-up request, which has no logged-in user (same trick as the demo seeder)."""

    rank = 10_000

    def __init__(self, user_id: int):
        self.user = type("U", (), {"id": user_id})


def apply_at_signup(db: Session, inv: RoleInvite, user: User, emp: Employee, request: Request | None) -> None:
    """Called inside sign-up, right after the account exists: swap the default Employee role for the invited one."""
    from app.modules.org.service import set_manager  # local import avoids a circular import

    role = db.get(Role, inv.role_id)
    db.query(UserRole).filter(UserRole.user_id == user.id).delete()
    db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=inv.created_by))
    inv.claimed_user_id, inv.claimed_at = user.id, clock.utcnow()
    if role.code in MANAGEMENT_ROLES:
        mgmt = db.scalar(select(Department).where(Department.code == MGMT_CODE))
        if mgmt is not None:
            emp.department_id = mgmt.id
        emp.job_title, emp.status = MANAGEMENT_ROLES[role.code], "active"
        db.flush()
        boss = None
        for code in BOSS_ROLES.get(role.code, []):
            boss = db.scalar(
                select(Employee.id).join(UserRole, UserRole.user_id == Employee.user_id).join(Role, Role.id == UserRole.role_id)
                .where(Role.code == code, Employee.status == "active", Employee.id != emp.id).order_by(Employee.id).limit(1)
            )  # fmt: skip
            if boss is not None:
                break
        if boss is not None:
            set_manager(db, _System(inv.created_by), emp.id, boss, request, audit_it=False)  # type: ignore[arg-type]
    db.flush()
    audit.log(db, user.id, "ROLE_INVITE_CLAIMED", "role_invite", inv.id, after={"email": inv.email, "role": role.code}, request=request)
