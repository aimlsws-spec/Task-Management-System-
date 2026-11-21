"""Who is "in the loop" on a task: the people it touches (assignee, assigner, head, QA, the project's head/QA/team) and the
review stages its finished work passes through (QA -> head -> CEO/Owner). Pure lookups on models: no rules, no side effects.

Head and QA come from the task itself, else its project, else the assignee's DEPARTMENT (its head / its QA tester) (ADR 008).
Every task an employee finishes is reviewed: QA (if any) -> head (if any) -> CEO/Owner. Owner/CEO's own tasks need no chain."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.org.models import Department, Employee
from app.modules.rbac.models import Role, UserRole
from app.modules.tasks.models import Project, ProjectMember, Task

STAGE_ORDER = ("qa", "head", "leadership")


def _active(db: Session, emp_id: int | None) -> Employee | None:
    e = db.get(Employee, emp_id) if emp_id else None
    return e if e is not None and e.status != "inactive" else None


def _assignee_department(db: Session, t: Task) -> Department | None:
    emp = db.get(Employee, t.assignee_id) if t.assignee_id else None
    return db.get(Department, emp.department_id) if emp is not None else None


def named_head_id(db: Session, t: Task) -> int | None:
    """A head somebody chose for this task or its project (not the department fallback)."""
    if t.head_employee_id:
        return t.head_employee_id
    pr = db.get(Project, t.project_id) if t.project_id else None
    return pr.head_employee_id if pr is not None else None


def named_qa_id(db: Session, t: Task) -> int | None:
    if t.qa_employee_id:
        return t.qa_employee_id
    pr = db.get(Project, t.project_id) if t.project_id else None
    return pr.qa_employee_id if pr is not None else None


def head_id(db: Session, t: Task) -> int | None:
    """The task's own head, else the project's head, else the head of the assignee's department (never the assignee)."""
    if t.head_employee_id:
        return t.head_employee_id
    pr = db.get(Project, t.project_id) if t.project_id else None
    if pr is not None and pr.head_employee_id:
        return pr.head_employee_id
    dept = _assignee_department(db, t)
    head = dept.head_employee_id if dept is not None else None
    return head if head and head != t.assignee_id else None


def qa_id(db: Session, t: Task) -> int | None:
    """The task's own QA, else the project's QA, else the QA tester of the assignee's department (never the assignee)."""
    if t.qa_employee_id:
        return t.qa_employee_id
    pr = db.get(Project, t.project_id) if t.project_id else None
    if pr is not None and pr.qa_employee_id:
        return pr.qa_employee_id
    dept = _assignee_department(db, t)
    qa = dept.qa_employee_id if dept is not None else None
    return qa if qa and qa != t.assignee_id else None


def is_leadership(db: Session, employee_id: int | None) -> bool:
    emp = db.get(Employee, employee_id) if employee_id else None
    if emp is None:
        return False
    return db.scalar(select(Role.id).join(UserRole, UserRole.role_id == Role.id)
                     .where(UserRole.user_id == emp.user_id, Role.code.in_(("owner", "ceo")))) is not None  # fmt: skip


def has_chain(db: Session, t: Task) -> bool:
    """Finished work is reviewed (QA -> head -> CEO/Owner) instead of the assignee completing it. Only work done by the
    Owner or CEO themselves is simply completed: nobody is above them to review it."""
    return not is_leadership(db, t.assignee_id)


def stages(db: Session, t: Task) -> list[str]:
    """The review stages this task's work passes through, in order. Nobody reviews their own work; the same person is not asked twice."""
    out: list[str] = []
    qa = _active(db, qa_id(db, t))
    if qa is not None and qa.id != t.assignee_id:
        out.append("qa")
    head = _active(db, head_id(db, t))
    if head is not None and head.id != t.assignee_id and (qa is None or head.id != qa.id or "qa" not in out):
        out.append("head")
    out.append("leadership")
    return out


def first_stage(db: Session, t: Task) -> str:
    return stages(db, t)[0]


def next_stage(db: Session, t: Task, current: str) -> str | None:
    """The stage after `current` (None = nothing left: the task is completed). Works even if `current` has since been removed."""
    rank = STAGE_ORDER.index(current)
    for s in stages(db, t):
        if STAGE_ORDER.index(s) > rank:
            return s
    return None


def loop_employee_ids(db: Session, t: Task) -> list[int]:
    """Everybody with a stake in this task, for messages: the task's people plus the project's head, QA, team and creator."""
    ids: list[int | None] = [t.assignee_id, t.assigned_by_id, head_id(db, t), qa_id(db, t)]
    if t.project_id:
        pr = db.get(Project, t.project_id)
        if pr is not None:
            ids += [pr.head_employee_id, pr.qa_employee_id, pr.owner_employee_id]
            ids += list(db.scalars(select(ProjectMember.employee_id).where(ProjectMember.project_id == pr.id)))
    seen: list[int] = []
    for i in ids:
        if i and i not in seen:
            seen.append(i)
    return seen


def is_in_loop(db: Session, t: Task, employee_id: int | None) -> bool:
    return employee_id is not None and employee_id in loop_employee_ids(db, t)
