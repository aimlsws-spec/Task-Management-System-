"""Seed data for roles/permissions (doc 03). Idempotent; roles and scopes remain editable at runtime."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.audit.models import SystemSetting
from app.modules.rbac.models import Permission, Role, RolePermission

log = logging.getLogger("tms.rbac")

# Bump when the default matrix changes; system roles are then reset to the new defaults once.
SEED_VERSION = 4  # v4: Owner and CEO no longer hold audit.view (ADR 002)

# code -> (category, description)
PERMISSIONS: dict[str, tuple[str, str]] = {
    "task.view": ("task", "View tasks"),
    "task.create": ("task", "Create tasks"),
    "task.assign": ("task", "Assign tasks to employees"),
    "task.edit": ("task", "Edit task fields"),
    "task.reassign": ("task", "Reassign tasks"),
    "task.priority.change": ("task", "Change priority"),
    "task.deadline.edit": ("task", "Edit / extend deadlines"),
    "task.verify": ("task", "Verify or revert completed tasks"),
    "task.cancel": ("task", "Cancel tasks"),
    "time.view": ("time", "View time logs"),
    "time.correct.approve": ("time", "Approve time corrections"),
    "delay.view": ("delay", "View delay explanations"),
    "delay.review": ("delay", "Review delay explanations"),
    "blocker.view": ("blocker", "View blockers"),
    "blocker.raise": ("blocker", "Raise blockers"),
    "blocker.manage": ("blocker", "Resolve / assign / escalate blockers"),
    "comment.create": ("comment", "Comment on tasks"),
    "report.view": ("report", "View reports"),
    "report.export": ("report", "Export reports"),
    "dashboard.view": ("dashboard", "View dashboard"),
    "employee.view": ("org", "View employees"),
    "employee.manage": ("org", "Create / edit / deactivate employees"),
    "department.manage": ("org", "Add, edit, delete departments and set heads"),
    "hierarchy.manage": ("org", "Manage reporting relationships"),
    "role.manage": ("admin", "Manage roles and permissions"),
    "project.manage": ("project", "Manage projects"),
    "settings.manage": ("admin", "System settings, calendar, sign-up rules"),
    "audit.view": ("admin", "View audit log"),
    "notification.rules.manage": ("admin", "Manage notification and reminder rules"),
}

# Organization setup belongs to the Admin panel only (not Owner / CEO / Manager).
ADMIN_ONLY = {
    "employee.manage", "department.manage", "hierarchy.manage", "role.manage",
    "settings.manage", "notification.rules.manage",
}  # fmt: skip

# roles: code -> (name, rank, description)
ROLES: dict[str, tuple[str, int, str]] = {
    "admin": ("Admin", 110, "System administrator: organization setup only, no task authority"),
    "owner": ("Owner", 100, "Highest business authority, organization-wide task control"),
    "ceo": ("CEO", 90, "Senior management, organization-wide visibility"),
    "manager": ("Manager", 70, "Supervises employees and department heads"),
    "department_head": ("Department Head", 50, "Runs a department"),
    "employee": ("Employee", 10, "Works on assigned tasks"),
}

_MGMT_TASK = [
    "task.view", "task.create", "task.assign", "task.edit", "task.reassign",
    "task.priority.change", "task.deadline.edit", "task.verify", "task.cancel",
    "time.view", "time.correct.approve", "delay.view", "delay.review",
    "blocker.view", "blocker.raise", "blocker.manage", "comment.create",
    "report.view", "report.export", "dashboard.view", "employee.view", "project.manage",
]  # fmt: skip


# Held by the Admin alone, on top of the org-setup permissions: Owner and CEO do not see the audit log.
ADMIN_ONLY_VIEW = {"audit.view"}


def _matrix() -> dict[str, dict[str, str]]:
    org = "organization"
    work = {c: org for c in PERMISSIONS if c not in ADMIN_ONLY and c not in ADMIN_ONLY_VIEW}  # all work, no org setup, no audit log
    admin = {c: org for c in ADMIN_ONLY} | {"employee.view": org, "audit.view": org, "dashboard.view": "self"}
    manager = {c: "team" for c in _MGMT_TASK}
    head = {c: "department" for c in _MGMT_TASK}
    employee = {
        c: "self"
        for c in (
            "task.view", "time.view", "delay.view", "blocker.view", "blocker.raise",
            "comment.create", "report.view", "report.export", "dashboard.view", "employee.view",
        )
    }  # fmt: skip
    return {"admin": admin, "owner": work, "ceo": dict(work), "manager": manager, "department_head": head, "employee": employee}


def seed_rbac(db: Session) -> None:
    perms = {p.code: p for p in db.scalars(select(Permission))}
    for code, (cat, desc) in PERMISSIONS.items():
        if code not in perms:
            perms[code] = Permission(code=code, category=cat, description=desc)
            db.add(perms[code])
    roles = {r.code: r for r in db.scalars(select(Role))}
    for code, (name, rank, desc) in ROLES.items():
        if code not in roles:
            roles[code] = Role(code=code, name=name, rank=rank, description=desc, is_system=True)
            db.add(roles[code])
    db.flush()

    row = db.get(SystemSetting, "rbac_seed_version")
    current = row.value if row is not None and isinstance(row.value, int) else 0
    have_grants = {rp.role_id for rp in db.scalars(select(RolePermission))}
    for role_code, grants in _matrix().items():
        role = roles[role_code]
        outdated = current < SEED_VERSION and role.id in have_grants
        if outdated:
            log.warning("Resetting system role '%s' to seed v%s defaults", role_code, SEED_VERSION)
            db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        if outdated or role.id not in have_grants:
            for perm_code, scope in grants.items():
                db.add(RolePermission(role_id=role.id, permission_id=perms[perm_code].id, scope=scope))
    if row is None:
        db.add(SystemSetting(key="rbac_seed_version", value=SEED_VERSION))
    elif current < SEED_VERSION:
        row.value = SEED_VERSION
    db.flush()
