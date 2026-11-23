"""Who is "in the loop" on a task: the people it touches (assignee, assigner, head, QA, the project's head/QA/team) and the
review stages its finished work passes through (QA -> head -> CEO/Owner). Pure lookups on models: no rules, no side effects.

Head and QA come from the task itself, else its project, else the assignee's DEPARTMENT (its head / its QA tester) (ADR 008).
Every task an employee finishes is reviewed: QA (if any) -> head (if any) -> CEO/Owner. Owner/CEO's own tasks need no chain."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.org.models import Department, Employee
from app.modules.rbac.models import Role, UserRole
from app.modules.tasks.models import Project, ProjectHead, ProjectMember, ProjectQAMember, Task, TaskHead, TaskQAMember

STAGE_ORDER = ("qa", "head", "leadership")


def _active(db: Session, emp_id: int | None) -> Employee | None:
    e = db.get(Employee, emp_id) if emp_id else None
    return e if e is not None and e.status != "inactive" else None


def _assignee_department(db: Session, t: Task) -> Department | None:
    emp = db.get(Employee, t.assignee_id) if t.assignee_id else None
    return db.get(Department, emp.department_id) if emp is not None else None


def task_head_ids(db: Session, t: Task) -> list[int]:
    """Returns explicit task head IDs from task_heads table and/or head_employee_id/sub_head_employee_id."""
    ids = list(db.scalars(select(TaskHead.employee_id).where(TaskHead.task_id == t.id)))
    for h in (t.head_employee_id, getattr(t, "sub_head_employee_id", None)):
        if h and h not in ids:
            ids.append(h)
    return ids


def project_head_ids(db: Session, pr: Project) -> list[int]:
    """Returns explicit project head IDs from project_heads table and/or head_employee_id/sub_head_employee_id."""
    ids = list(db.scalars(select(ProjectHead.employee_id).where(ProjectHead.project_id == pr.id)))
    for h in (pr.head_employee_id, getattr(pr, "sub_head_employee_id", None)):
        if h and h not in ids:
            ids.append(h)
    return ids


def effective_heads(db: Session, t: Task) -> list[int]:
    """
    Returns the list of responsible heads/subheads for this task following the 4-tier fallback:
    1. Explicit task head/subhead if set (supports multiple heads).
    2. Else explicit project head/subhead if set (supports multiple heads).
    3. Else fallback to the assignee's department head and subhead.
    4. If department has no head and no subhead: returns [] (specific employee task).
    Excludes the assignee themselves (cannot review self).
    """
    heads: list[int] = []
    # 1. Task level
    t_heads = task_head_ids(db, t)
    if t_heads:
        for h in t_heads:
            if h not in heads:
                heads.append(h)
    # 2. Project level
    elif t.project_id:
        pr = db.get(Project, t.project_id)
        if pr:
            pr_heads = project_head_ids(db, pr)
            for h in pr_heads:
                if h not in heads:
                    heads.append(h)
    # 3. Department fallback
    if not heads:
        dept = _assignee_department(db, t)
        if dept:
            from app.modules.org import models as org_models
            dl = org_models.department_leaders(db, dept.id)
            for h in dl["heads"] + dl["sub_heads"]:
                if h and h not in heads:
                    heads.append(h)

    # Filter out inactive employees and assignee (cannot review self)
    valid = []
    for h in heads:
        if h != t.assignee_id and _active(db, h) is not None:
            valid.append(h)
    return valid


def named_head_id(db: Session, t: Task) -> int | None:
    """A head somebody chose for this task or its project (not the department fallback)."""
    t_heads = task_head_ids(db, t)
    if t_heads:
        return t_heads[0]
    if t.project_id:
        pr = db.get(Project, t.project_id)
        if pr:
            pr_heads = project_head_ids(db, pr)
            if pr_heads:
                return pr_heads[0]
    return None


def head_id(db: Session, t: Task) -> int | None:
    """The primary head ID among the effective heads."""
    heads = effective_heads(db, t)
    return heads[0] if heads else None


def sub_head_id(db: Session, t: Task) -> int | None:
    """The subhead ID if more than one effective head is present or subhead explicitly set."""
    heads = effective_heads(db, t)
    return heads[1] if len(heads) > 1 else None


def qa_ids(db: Session, t: Task) -> list[int]:
    """
    Returns all assigned QA member employee IDs:
    1. Task-level QA members (from task_qa_members or t.qa_employee_id).
    2. Else project-level QA members (from project_qa_members or pr.qa_employee_id).
    3. Else department QA tester.
    Excludes the assignee themselves and inactive employees.
    """
    members: list[int] = list(db.scalars(select(TaskQAMember.employee_id).where(TaskQAMember.task_id == t.id)))
    if not members and t.qa_employee_id:
        members = [t.qa_employee_id]

    if not members and t.project_id:
        members = list(db.scalars(select(ProjectQAMember.employee_id).where(ProjectQAMember.project_id == t.project_id)))
        if not members:
            pr = db.get(Project, t.project_id)
            if pr and pr.qa_employee_id:
                members = [pr.qa_employee_id]

    if not members:
        dept = _assignee_department(db, t)
        if dept and dept.qa_employee_id:
            members = [dept.qa_employee_id]

    valid = []
    for m in members:
        if m != t.assignee_id and _active(db, m) is not None and m not in valid:
            valid.append(m)
    return valid


def qa_id(db: Session, t: Task) -> int | None:
    """Primary QA member for backwards-compatibility."""
    qas = qa_ids(db, t)
    return qas[0] if qas else None


def named_qa_id(db: Session, t: Task) -> int | None:
    if t.qa_employee_id:
        return t.qa_employee_id
    pr = db.get(Project, t.project_id) if t.project_id else None
    return pr.qa_employee_id if pr is not None else None


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
    # 1. QA stage if task has QA assigned
    if qa_ids(db, t):
        out.append("qa")
    # 2. Head stage if task has any effective head/subhead (skipped if specific employee task)
    heads = effective_heads(db, t)
    if heads:
        out.append("head")
    # 3. Leadership stage
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
    ids: list[int | None] = [t.assignee_id, t.assigned_by_id]
    ids.extend(effective_heads(db, t))
    ids.extend(qa_ids(db, t))
    # Also keep department head and subhead in loop
    dept = _assignee_department(db, t)
    if dept:
        if dept.head_employee_id:
            ids.append(dept.head_employee_id)
        if getattr(dept, "sub_head_employee_id", None):
            ids.append(dept.sub_head_employee_id)
    if t.project_id:
        pr = db.get(Project, t.project_id)
        if pr is not None:
            ids += [pr.head_employee_id, getattr(pr, "sub_head_employee_id", None), pr.qa_employee_id, pr.owner_employee_id]
            ids += project_head_ids(db, pr)
            ids += list(db.scalars(select(ProjectMember.employee_id).where(ProjectMember.project_id == pr.id)))
            ids += list(db.scalars(select(ProjectQAMember.employee_id).where(ProjectQAMember.project_id == pr.id)))
    seen: list[int] = []
    for i in ids:
        if i and i not in seen:
            seen.append(i)
    return seen


def is_in_loop(db: Session, t: Task, employee_id: int | None) -> bool:
    return employee_id is not None and employee_id in loop_employee_ids(db, t)
