"""Idempotent seeders. Never run from migrations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, validate_password_policy
from app.modules.auth.models import User
from app.modules.notifications.seed import seed_notifications
from app.modules.org import codes
from app.modules.org.models import Department, Employee
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.seed import seed_rbac
from app.modules.tasks.models import TaskCategory, TaskType
from app.modules.workcal.service import seed_default_calendar

# (name, code, is_system). System departments are not selectable at sign-up and cannot be deleted.
# Every other department is created by the Admin in the Admin panel; nothing is pre-filled.
DEPARTMENTS = [("Management", "MGMT", True), ("Unassigned", "UNASSIGNED", True)]


CATEGORIES = ["Development", "Bug fix", "Design", "Documentation", "Marketing", "HR", "Sales", "Support", "Accounts", "General"]
TYPES = [("Task", False), ("Feature", False), ("Bug", False), ("Research", False), ("Review", True)]  # (name, requires_review)


def seed_core(db: Session) -> None:
    seed_rbac(db)
    seed_default_calendar(db)
    seed_notifications(db)
    for name, code, system in DEPARTMENTS:
        dept = db.scalar(select(Department).where(Department.code == code))
        if dept is None:
            dept = Department(name=name, code=code)
            db.add(dept)
        if system:  # keep system flags correct on existing databases too
            dept.is_system, dept.self_service = True, False
    for name in CATEGORIES:
        if not db.scalar(select(TaskCategory.id).where(TaskCategory.name == name)):
            db.add(TaskCategory(name=name))
    for name, review in TYPES:
        if not db.scalar(select(TaskType.id).where(TaskType.name == name)):
            db.add(TaskType(name=name, requires_review=review))
    db.flush()


def create_user_employee(
    db: Session, email: str, password: str, full_name: str, code: str, dept_code: str,
    role_code: str, job_title: str | None = None, must_change: bool = False,
) -> Employee:  # fmt: skip
    validate_password_policy(password)
    user = User(email=email.lower(), password_hash=hash_password(password), must_change_password=must_change)
    db.add(user)
    db.flush()
    dept = db.scalar(select(Department).where(Department.code == dept_code))
    emp = Employee(user_id=user.id, employee_code=code, full_name=full_name, department_id=dept.id, job_title=job_title)
    db.add(emp)
    role = db.scalar(select(Role).where(Role.code == role_code))
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if role_code == "admin":  # the Admin runs the system; they are not given tasks
        emp.can_receive_tasks = False
    db.flush()
    return emp


def bootstrap_admin(db: Session, email: str, password: str, full_name: str = "Administrator") -> Employee:
    """First real account on a fresh system: the Admin, who then creates everyone else."""
    seed_core(db)
    if db.scalar(select(User.id).where(User.email == email.lower())):
        raise SystemExit("A user with that email already exists")
    return create_user_employee(db, email, password, full_name, codes.generate(db), "MGMT", "admin", "System Administrator")
