"""Authorization = permission (RBAC) AND scope (reporting tree / department / self)."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.org.models import Employee, ManagerDepartment, ReportingRelationship
from app.modules.rbac.models import SCOPES, Permission, Role, RolePermission, UserRole

SCOPE_ORDER = {s: i for i, s in enumerate(SCOPES)}


def subtree_ids(db: Session, root_employee_id: int) -> set[int]:
    """All employees below `root` in the *current* reporting tree (UNION => terminates on cycles)."""
    rr = ReportingRelationship
    base = select(rr.employee_id.label("eid")).where(
        rr.reports_to_id == root_employee_id, rr.effective_to.is_(None)
    )
    cte = base.cte("sub", recursive=True)
    rec = select(rr.employee_id).join(cte, rr.reports_to_id == cte.c.eid).where(rr.effective_to.is_(None))
    cte = cte.union(rec)
    return set(db.scalars(select(cte.c.eid)))


def effective_permissions(db: Session, user_id: int) -> tuple[dict[str, str], list[str], int]:
    """Union of all roles; the widest scope wins per permission. Returns (perms, role_codes, max_rank)."""
    rows = db.execute(
        select(Permission.code, RolePermission.scope)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    ).all()
    perms: dict[str, str] = {}
    for code, scope in rows:
        if code not in perms or SCOPE_ORDER[scope] > SCOPE_ORDER[perms[code]]:
            perms[code] = scope
    roles = db.execute(
        select(Role.code, Role.rank).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ).all()
    return perms, sorted(r[0] for r in roles), max((r[1] for r in roles), default=0)


def user_max_rank(db: Session, user_id: int) -> int:
    from sqlalchemy import func

    return db.scalar(select(func.max(Role.rank)).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)) or 0


@dataclass
class Principal:
    db: Session
    user: User
    employee: Employee | None
    permissions: dict[str, str]
    roles: list[str]
    rank: int
    _cache: dict[str, set[int] | None] = field(default_factory=dict)

    def has(self, code: str) -> bool:
        return code in self.permissions

    def scope(self, code: str) -> str | None:
        return self.permissions.get(code)

    def scope_employee_ids(self, code: str) -> set[int] | None:
        """None = organization-wide (no filter). Empty set = nothing visible."""
        scope = self.scope(code)
        if scope is None:
            return set()
        if scope == "organization":
            return None
        key = scope
        if key in self._cache:
            return self._cache[key]
        ids: set[int] = set()
        me = self.employee
        if me is not None:
            ids.add(me.id)
            if scope == "team":
                ids |= subtree_ids(self.db, me.id)
                dept_ids = list(
                    self.db.scalars(select(ManagerDepartment.department_id).where(ManagerDepartment.employee_id == me.id))
                )
                if dept_ids:
                    ids |= set(self.db.scalars(select(Employee.id).where(Employee.department_id.in_(dept_ids))))
            elif scope == "department":
                from app.modules.org.models import Department

                dept_ids = list(self.db.scalars(select(Department.id).where(Department.head_employee_id == me.id)))
                if dept_ids:
                    ids |= set(self.db.scalars(select(Employee.id).where(Employee.department_id.in_(dept_ids))))
        self._cache[key] = ids
        return ids

    def can_see(self, code: str, employee_id: int) -> bool:
        ids = self.scope_employee_ids(code)
        return ids is None or employee_id in ids
