"""Task use cases. Authorization = permission AND scope AND object rules (rank, ownership, status machine)."""

from datetime import date, datetime, time, timedelta

from fastapi import Request
from sqlalchemy import and_, case, false, func, or_, select, true
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError, Forbidden, NotFound
from app.core.grace import late_cutoff
from app.modules.audit import service as audit
from app.modules.audit.models import ActivityLog
from app.modules.auth.models import User
from app.modules.org.models import Department, Employee
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.policy import Principal, user_max_rank
from app.modules.tasks import loop
from app.modules.tasks import state_machine as sm
from app.modules.tasks.models import (
    OPEN_STATUSES,
    PRIORITIES,
    PRIORITY_RANK,
    TERMINAL,
    ExtensionRequest,
    Project,
    ProjectHead,
    ProjectQAMember,
    Task,
    TaskAssignment,
    TaskCategory,
    TaskDeadlineHistory,
    TaskHead,
    TaskQAMember,
    TaskStatusHistory,
    TaskType,
)
from app.modules.timetracking import queries as tq
from app.modules.workcal import service as cal

DEFAULT_ESTIMATE_HOURS = 8  # nobody types an effort estimate any more; this keeps workload numbers defined
SELF_STATES = ("active", "on_leave")  # employees who can hold tasks
LEADERSHIP_ROLES = {"owner", "ceo"}


def is_leadership(p: Principal) -> bool:
    return bool(set(p.roles) & LEADERSHIP_ROLES) or getattr(p, "is_owner", False)


def z(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


# ------------------------------------------------------------------ visibility / authorization


def visible_clause(p: Principal):
    """Tasks I may see: held by someone in my `task.view` scope, or created (assigned) by me, or where I am head/subhead/QA."""
    cids = p.company_ids()
    company_filter = Task.company_id.in_(cids) if cids is not None else true()
    ids = p.scope_employee_ids("task.view")
    if ids is None:
        return company_filter
    me = p.employee.id if p.employee else -1
    heads_project = Task.project_id.in_(
        select(Project.id).where(
            or_(
                Project.head_employee_id == me,
                Project.sub_head_employee_id == me,
                Project.qa_employee_id == me,
                Project.id.in_(select(ProjectQAMember.project_id).where(ProjectQAMember.employee_id == me)),
                Project.id.in_(select(ProjectHead.project_id).where(ProjectHead.employee_id == me)),
            )
        )
    )
    tests_dept = Task.assignee_id.in_(
        select(Employee.id).where(
            Employee.department_id.in_(
                select(Department.id).where(
                    or_(
                        Department.qa_employee_id == me,
                        Department.head_employee_id == me,
                        Department.sub_head_employee_id == me,
                    )
                )
            )
        )
    )
    task_qa = Task.id.in_(select(TaskQAMember.task_id).where(TaskQAMember.employee_id == me))
    task_head = Task.id.in_(select(TaskHead.task_id).where(TaskHead.employee_id == me))
    return and_(
        company_filter,
        or_(
            Task.assignee_id.in_(ids),
            Task.assigned_by_id == me,
            Task.head_employee_id == me,
            Task.sub_head_employee_id == me,
            task_head,
            Task.qa_employee_id == me,
            task_qa,
            heads_project,
            tests_dept,
        ),
    )


def get_visible_task(db: Session, p: Principal, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if t is None or not p.can_access_company(getattr(t, "company_id", 1)):
        raise NotFound("Task")
    ids = p.scope_employee_ids("task.view")
    if ids is None:
        return t
    me = p.employee.id if p.employee else -1
    if (
        t.assignee_id in ids
        or t.assigned_by_id == me
        or t.head_employee_id == me
        or getattr(t, "sub_head_employee_id", None) == me
        or t.qa_employee_id == me
    ):
        return t
    if db.scalar(select(TaskQAMember.task_id).where(TaskQAMember.task_id == t.id, TaskQAMember.employee_id == me)):
        return t
    if t.project_id is not None:
        heads_it = db.scalar(
            select(Project.id).where(
                Project.id == t.project_id,
                or_(
                    Project.head_employee_id == me,
                    Project.sub_head_employee_id == me,
                    Project.qa_employee_id == me,
                    Project.id.in_(select(ProjectQAMember.project_id).where(ProjectQAMember.employee_id == me)),
                ),
            )
        ) is not None
        if heads_it:
            return t
    dept_match = db.scalar(
        select(Employee.id).join(Department, Department.id == Employee.department_id).where(
            Employee.id == t.assignee_id,
            or_(
                Department.qa_employee_id == me,
                Department.head_employee_id == me,
                Department.sub_head_employee_id == me,
            ),
        )
    ) is not None
    if dept_match:
        return t
    raise NotFound("Task")


def can_manage(p: Principal, t: Task, perm: str) -> bool:
    """Holds `perm` and the task belongs to someone in that permission's scope, or I created it, or I am responsible head/subhead."""
    if not p.has(perm):
        return False
    me = p.employee.id if p.employee else -1
    if t.assigned_by_id == me or p.can_see(perm, t.assignee_id):
        return True
    if me > 0:
        if t.head_employee_id == me or getattr(t, "sub_head_employee_id", None) == me:
            return True
        if p.db.scalar(select(TaskHead.id).where(TaskHead.task_id == t.id, TaskHead.employee_id == me)):
            return True
    return False


def is_peer_head(db: Session, p: Principal, assignee: Employee) -> bool:
    """Department Heads may hand work to each other (across departments); the Manager and leadership are told."""
    if not p.has("task.assign") or "department_head" not in p.roles:
        return False
    from app.modules.notifications.resolver import role_codes

    if p.employee and assignee:
        from app.modules.org import models as org_models
        p_cids = org_models.employee_company_ids(db, p.employee)
        a_cids = org_models.employee_company_ids(db, assignee)
        if p_cids is not None and a_cids is not None and not (p_cids & a_cids):
            return False
    return "department_head" in role_codes(db, assignee.user_id)


def assert_assignable(db: Session, p: Principal, assignee: Employee | None) -> Employee:
    """Who may receive a task from this person: in their assign-scope, not above their rank, not themselves."""
    if assignee is None:
        raise NotFound("Employee")  # outside scope == not found
    from app.modules.org import models as org_models
    emp_cids = org_models.employee_company_ids(db, assignee)
    if emp_cids is not None and p.company_ids() is not None:
        if not (emp_cids & set(p.company_ids())):
            raise NotFound("Employee")
    if not (p.can_see("task.assign", assignee.id) or is_peer_head(db, p, assignee)):
        raise NotFound("Employee")  # outside scope == not found
    if p.employee is not None and assignee.id == p.employee.id:
        raise AppError("SELF_ASSIGN_NOT_ALLOWED", "You cannot assign a task to yourself", 422)
    user = db.get(User, assignee.user_id)
    if not user.is_active or assignee.status not in SELF_STATES or not assignee.can_receive_tasks:
        raise AppError("ASSIGNEE_UNAVAILABLE", "This person cannot receive tasks right now", 422)
    if user_max_rank(db, assignee.user_id) > p.rank:
        raise Forbidden("Tasks cannot be assigned upward to someone who outranks you")
    return assignee


# ------------------------------------------------------------------ deadlines


def resolve_due(db: Session, due_date: date) -> datetime:
    """A deadline is a DATE: it falls at the end of that working day (EOD, 18:30 by default). There is no deadline time."""
    return cal.resolve_eod_utc(db, due_date)


# ------------------------------------------------------------------ serialization


def _person(e: Employee | None) -> dict | None:
    if e is None:
        return None
    return {"id": e.id, "full_name": e.full_name, "job_title": e.job_title, "department_id": e.department_id,
            "employee_code": e.employee_code}  # fmt: skip


def is_overdue(t: Task, now: datetime | None = None) -> bool:
    return t.status not in TERMINAL and t.due_at < late_cutoff(now or clock.utcnow())


def task_dict(db: Session, t: Task, assignee: Employee | None = None, assigner: Employee | None = None, detail: bool = False) -> dict:
    now = clock.utcnow()
    assignee = assignee or db.get(Employee, t.assignee_id)
    assigner = assigner or db.get(Employee, t.assigned_by_id)
    from app.modules.org.models import Company
    comp = db.get(Company, getattr(t, "company_id", 1)) if getattr(t, "company_id", None) else None
    company_obj = {"id": comp.id, "name": comp.name, "code": comp.code} if comp else None
    out = {
        "id": t.id, "task_no": t.task_no, "title": t.title, "status": t.status, "priority": t.priority,
        "company_id": getattr(t, "company_id", 1),
        "company": company_obj,
        "assignee": _person(assignee), "assigned_by": _person(assigner), "department_id": t.department_id,
        "head": _person(db.get(Employee, loop.head_id(db, t))) if loop.head_id(db, t) else None,
        "sub_head": _person(db.get(Employee, loop.sub_head_id(db, t))) if loop.sub_head_id(db, t) else None,
        "heads": [_person(db.get(Employee, eid)) for eid in loop.effective_heads(db, t)],
        "qa": _person(db.get(Employee, loop.qa_id(db, t))) if loop.qa_id(db, t) else None,
        "qa_members": [_person(db.get(Employee, eid)) for eid in loop.qa_ids(db, t)],
        "project_id": t.project_id, "category_id": t.category_id, "type_id": t.type_id,
        "assigned_at": z(t.assigned_at), "start_date": t.start_date.isoformat() if t.start_date else None,
        "original_due_at": z(t.original_due_at), "due_at": z(t.due_at), "extension_count": t.extension_count,
        "estimated_hours": round(t.estimated_seconds / 3600, 2), "progress_pct": t.progress_pct,
        "is_overdue": is_overdue(t, now), "requires_review": t.requires_review, "version": t.version, "review_stage": t.review_stage,
        "acknowledged_at": z(t.acknowledged_at), "completed_at": z(t.completed_at),
    }  # fmt: skip
    if detail:
        assignments = db.scalars(select(TaskAssignment).where(TaskAssignment.task_id == t.id).order_by(TaskAssignment.assigned_at.asc())).all()
        history = []
        for a in assignments:
            assignee_emp = db.get(Employee, a.assignee_id)
            assigner_emp = db.get(Employee, a.assigned_by_id)
            history.append({
                "id": a.id,
                "assignee": _person(assignee_emp),
                "assigned_by": _person(assigner_emp),
                "assigned_at": z(a.assigned_at),
                "unassigned_at": z(a.unassigned_at),
                "reason": a.reason,
            })
        out |= {"description": t.description, "instructions": t.instructions, "special_note": t.instructions, "deadline_version": t.deadline_version,
                "cancelled_at": z(t.cancelled_at), "cancel_reason": t.cancel_reason,
                "assignment_history": history,
                "project": db.scalar(select(Project.name).where(Project.id == t.project_id)) if t.project_id else None,
                "category": db.scalar(select(TaskCategory.name).where(TaskCategory.id == t.category_id)) if t.category_id else None,
                "type": db.scalar(select(TaskType.name).where(TaskType.id == t.type_id)) if t.type_id else None}  # fmt: skip
    return out


def self_blocked(p: Principal, t: Task) -> bool:
    """Nobody verifies, reviews or reverts their own work (the Owner is the one exception)."""
    return bool(p.employee and p.employee.id == t.assignee_id and p.rank < 100)


def allowed_actions(p: Principal, t: Task) -> list[str]:
    acts: list[str] = []
    me = p.employee.id if p.employee else -1
    mine = t.assignee_id == me
    if mine:  # the employee's own work
        if get_settings().time_tracking:
            running = tq.open_session(p.db, me)
            running_here = running is not None and running.task_id == t.id
            if t.status in ("assigned", "acknowledged", "reopened", "in_progress") and not running_here:
                acts.append("start")
            if running_here:
                acts += ["pause", "stop"]
        elif t.status in ("assigned", "acknowledged", "reopened"):  # deadlines only: "start" just begins the work
            acts.append("start")
        if t.status in ("acknowledged", "in_progress", "on_hold", "blocked", "reopened"):
            acts.append("progress")
        if t.status == "in_progress":
            acts.append("hold")
            if not t.requires_review:
                acts.append("complete")
            acts.append("submit_for_review")
    if mine and t.status in ("assigned", "acknowledged", "in_progress", "on_hold", "reopened", "blocked") and p.has("blocker.raise"):
        acts.append("raise_blocker")
    manages_hold = can_manage(p, t, "task.assign")
    if not mine and manages_hold and t.status in ("in_progress", "on_hold"):
        acts.append("hold" if t.status == "in_progress" else "unhold")
    if mine and t.status == "on_hold":
        acts.append("unhold")
    from app.modules.tasks import projects as proj  # imported here: projects builds on this module

    if t.review_stage:  # project work: it is the project head's turn, then the CEO's or Owner's
        if proj.my_turn_to_review(p.db, p, t):
            acts.append("review")
    elif can_manage(p, t, "task.verify") and not self_blocked(p, t) and t.status == "under_review":
        acts.append("review")
    if can_manage(p, t, "task.verify") and not self_blocked(p, t):  # management's side of finished work
        if t.status == "completed":
            acts.append("revert")
            if t.verified_at is None:
                acts.append("verify")
    if t.status in OPEN_STATUSES:
        if is_leadership(p) and can_manage(p, t, "task.edit"):
            acts.append("edit")
        is_owner = "owner" in p.roles or getattr(p, "is_owner", False)
        if not is_owner and can_manage(p, t, "task.reassign"):
            acts.append("reassign")
        if can_manage(p, t, "task.priority.change"):
            acts.append("change_priority")
        if is_leadership(p) and can_manage(p, t, "task.cancel"):
            acts.append("cancel")
        if "ceo" in p.roles and p.can_access_company(t.company_id):
            acts.append("submit_to_owner")
    # --- deadlines and delay accountability (Phase 5)
    from app.modules.tasks import delays  # imported here: delays itself builds on this module

    st = delays.state_for(p.db, t)
    if mine and t.status in delays.REQUIRED_STATUSES:
        if st["overdue"] or st["explanations"]:
            acts.append("explain_delay")
        pending = p.db.scalar(select(ExtensionRequest.id).where(ExtensionRequest.task_id == t.id, ExtensionRequest.status == "pending"))
        if pending is None:
            acts.append("request_extension")
    if t.status in OPEN_STATUSES and can_manage(p, t, "task.deadline.edit"):
        acts.append("change_deadline")
    pending_for_me = st["escalated"] if delays.is_leadership(p) else st["awaiting_review"]  # CEO/Owner: only what was escalated up
    if pending_for_me and not st["required"] and can_manage(p, t, "delay.review") and not (mine and p.rank < 100):
        acts.append("review_delay")
    return acts


# ------------------------------------------------------------------ use cases


def _log(db, p, action, t, before=None, after=None, request=None):
    audit.log(db, p.user.id, action, "task", t.id, before=before, after=after, request=request, task_id=t.id)


def create_task(db: Session, p: Principal, d: dict, request: Request) -> tuple[Task, list[str]]:
    assignee = assert_assignable(db, p, db.get(Employee, d["assignee_id"]))
    now = clock.utcnow()
    project_id = d.get("project_id")
    due_date = d.get("due_date")
    if due_date is None:
        if project_id:
            pr = db.get(Project, project_id)
            if pr and pr.ends_on:
                due_date = pr.ends_on
            else:
                due_date = cal.utc_to_local(db, now).date()
        else:
            raise AppError("DEADLINE_REQUIRED", "A task without a project needs a deadline date", 422)
    due = resolve_due(db, due_date)
    if due <= now:
        raise AppError("PAST_DEADLINE", "The deadline must be in the future", 422)
    start_date = d.get("start_date") or cal.utc_to_local(db, now).date()
    if start_date > due_date:
        raise AppError("INVALID_START_DATE", "Start date cannot be after the deadline", 422)

    for model, key, label in ((Project, "project_id", "Project"), (TaskCategory, "category_id", "Category"), (TaskType, "type_id", "Type")):
        if d.get(key) is not None and db.get(model, d[key]) is None:
            raise AppError("INVALID_REFERENCE", f"{label} not found", 422)
    from app.modules.tasks import projects as proj  # imported here: projects builds on this module

    project = proj.assert_can_take_task(db, d["project_id"], assignee.id) if d.get("project_id") else None

    if project:
        company_id = getattr(project, "company_id", 1)
    else:
        company_id = d.get("company_id") or (p.employee.company_id if p.employee and getattr(p.employee, "company_id", None) else getattr(assignee, "company_id", 1))

    if not p.can_access_company(company_id):
        raise Forbidden("You cannot create tasks for this company")

    from app.modules.org import models as org_models
    assignee_cids = org_models.employee_company_ids(db, assignee)
    if assignee_cids is not None and company_id not in assignee_cids:
        raise Forbidden(f"Assignee '{assignee.full_name}' does not belong to the selected company")
    head_ids = d.get("head_employee_ids")
    head_id = d.get("head_employee_id")
    sub_head_id = d.get("sub_head_employee_id")
    qa_id = d.get("qa_employee_id")
    qa_ids = d.get("qa_employee_ids")
    if qa_ids is None and qa_id:
        qa_ids = [qa_id]
    elif qa_ids and not qa_id:
        qa_id = qa_ids[0]

    if not project:
        if not head_ids and not head_id and not sub_head_id:
            dept = db.get(Department, assignee.department_id)
            if dept:
                from app.modules.org import models as org_models
                dl = org_models.department_leaders(db, dept.id)
                fallback_heads = [h for h in (dl["heads"] + dl["sub_heads"]) if h != assignee.id]
                if fallback_heads:
                    head_ids = fallback_heads
        if not qa_ids:
            dept = db.get(Department, assignee.department_id)
            if dept and dept.qa_employee_id and dept.qa_employee_id != assignee.id:
                qa_ids = [dept.qa_employee_id]
                qa_id = dept.qa_employee_id

    if head_ids and not head_id:
        head_id = head_ids[0]
        if len(head_ids) > 1 and not sub_head_id:
            sub_head_id = head_ids[1]
    elif not head_ids and (head_id or sub_head_id):
        head_ids = [h for h in (head_id, sub_head_id) if h]

    def _assert_task_emp_company(emp_id: int | None, role_name: str):
        if not emp_id:
            return
        emp = proj.check_person(db, emp_id, role_name)
        cids = org_models.employee_company_ids(db, emp)
        if cids is not None and company_id not in cids:
            raise Forbidden(f"{role_name.capitalize()} '{emp.full_name}' does not belong to the task's company")

    for hid in (head_ids or []):
        _assert_task_emp_company(hid, "head")
    for qid in (qa_ids or []):
        _assert_task_emp_company(qid, "QA")

    creator_emp_id = p.employee.id if p.employee else assignee.id
    ttype = db.get(TaskType, d["type_id"]) if d.get("type_id") else None
    instructions = d.get("special_note") or d.get("instructions")
    t = Task(
        task_no=f"TMP-{now.timestamp()}-{assignee.id}", title=d["title"], description=d["description"],
        instructions=instructions, project_id=d.get("project_id"), department_id=assignee.department_id,
        company_id=company_id, category_id=d.get("category_id"), type_id=d.get("type_id"), assignee_id=assignee.id,
        head_employee_id=head_id, sub_head_employee_id=sub_head_id, qa_employee_id=qa_id, assigned_by_id=creator_emp_id, priority=d["priority"], priority_rank=PRIORITY_RANK[d["priority"]],
        assigned_at=now, start_date=start_date, original_due_at=due, due_at=due,
        estimated_seconds=int(round((d.get("estimated_hours") or DEFAULT_ESTIMATE_HOURS) * 3600)), requires_review=bool(ttype and ttype.requires_review),
    )  # fmt: skip
    db.add(t)
    db.flush()
    t.task_no = f"TSK-{t.id:06d}"

    if head_ids:
        for hid in dict.fromkeys(head_ids):
            db.add(TaskHead(task_id=t.id, employee_id=hid))

    if qa_ids:
        for qid in set(qa_ids):
            proj.check_person(db, qid, "QA")
            db.add(TaskQAMember(task_id=t.id, employee_id=qid))

    db.add(TaskAssignment(task_id=t.id, assignee_id=assignee.id, assigned_by_id=creator_emp_id, assigned_at=now))
    db.add(TaskStatusHistory(task_id=t.id, from_status=None, to_status="assigned", changed_by_user_id=p.user.id, created_at=now))
    db.add(TaskDeadlineHistory(task_id=t.id, deadline_version=1, previous_due_at=None, new_due_at=due,
                               changed_by_user_id=p.user.id, change_type="initial", created_at=now))  # fmt: skip
    _log(db, p, "TASK_CREATED", t, after={"task_no": t.task_no, "title": t.title, "assignee_id": assignee.id,
                                          "priority": t.priority, "due_at": z(due), "head_employee_id": t.head_employee_id,
                                          "sub_head_employee_id": t.sub_head_employee_id,
                                          "qa_employee_id": t.qa_employee_id}, request=request)  # fmt: skip
    proj.on_task_created(db, p, t, project, request)  # reopens a completed project, tells the head and QA
    warnings = [w for w in (cal.deadline_warning(db, due),) if w]
    db.flush()
    return t, warnings


EDITABLE = ("title", "description", "instructions", "start_date", "project_id", "category_id", "type_id", "estimated_hours",
            "head_employee_id", "sub_head_employee_id", "head_employee_ids", "qa_employee_id", "qa_employee_ids", "company_id")


def update_task(db: Session, p: Principal, t: Task, d: dict, request: Request) -> None:
    if not is_leadership(p) or not can_manage(p, t, "task.edit"):
        raise Forbidden("Only Owner and CEO have authority to edit tasks")
    if t.status not in OPEN_STATUSES:
        raise AppError("TASK_CLOSED", "Completed or cancelled tasks cannot be edited", 409)
    if "special_note" in d and d["special_note"] is not None:
        d["instructions"] = d["special_note"]
    target_comp = t.company_id
    if "company_id" in d and d["company_id"] != t.company_id:
        if not p.can_access_company(d["company_id"]):
            raise Forbidden("Access denied for this company")
        target_comp = d["company_id"]

    from app.modules.org import models as org_models

    def _assert_task_emp_company(emp_id: int | None, role_name: str):
        if not emp_id:
            return
        from app.modules.tasks import projects as proj
        emp = proj.check_person(db, emp_id, role_name)
        cids = org_models.employee_company_ids(db, emp)
        if cids is not None and target_comp not in cids:
            raise Forbidden(f"{role_name.capitalize()} '{emp.full_name}' does not belong to the task's company")

    if "head_employee_ids" in d and d["head_employee_ids"] is not None:
        for hid in d["head_employee_ids"]:
            _assert_task_emp_company(hid, "head")
    elif "head_employee_id" in d and d["head_employee_id"]:
        _assert_task_emp_company(d["head_employee_id"], "head")
    if "sub_head_employee_id" in d and d["sub_head_employee_id"]:
        _assert_task_emp_company(d["sub_head_employee_id"], "sub-head")
    if "qa_employee_ids" in d and d["qa_employee_ids"] is not None:
        for qid in d["qa_employee_ids"]:
            _assert_task_emp_company(qid, "QA")
    elif "qa_employee_id" in d and d["qa_employee_id"]:
        _assert_task_emp_company(d["qa_employee_id"], "QA")

    before, after = {}, {}
    if "company_id" in d and d["company_id"] != t.company_id:
        before["company_id"], after["company_id"] = t.company_id, d["company_id"]
        t.company_id = d["company_id"]
    if "head_employee_ids" in d and d["head_employee_ids"] is not None:
        from app.modules.tasks import projects as proj
        wanted = list(dict.fromkeys(d["head_employee_ids"]))
        for hid in wanted:
            proj.check_person(db, hid, "head")
        current = set(db.scalars(select(TaskHead.employee_id).where(TaskHead.task_id == t.id)))
        wanted_set = set(wanted)
        for hid in current - wanted_set:
            db.query(TaskHead).filter(TaskHead.task_id == t.id, TaskHead.employee_id == hid).delete()
        for hid in wanted_set - current:
            db.add(TaskHead(task_id=t.id, employee_id=hid))
        primary_head = wanted[0] if len(wanted) > 0 else None
        primary_sub = wanted[1] if len(wanted) > 1 else None
        t.head_employee_id = primary_head
        t.sub_head_employee_id = primary_sub
        before["heads"], after["heads"] = sorted(current), sorted(wanted_set)
    elif "sub_head_employee_id" in d and d["sub_head_employee_id"] != getattr(t, "sub_head_employee_id", None):
        if d["sub_head_employee_id"] is not None:
            from app.modules.tasks import projects as proj
            proj.check_person(db, d["sub_head_employee_id"], "sub-head")
        before["sub_head_employee_id"], after["sub_head_employee_id"] = getattr(t, "sub_head_employee_id", None), d["sub_head_employee_id"]
        t.sub_head_employee_id = d["sub_head_employee_id"]
    if "qa_employee_ids" in d and d["qa_employee_ids"] is not None:
        from app.modules.tasks import projects as proj
        wanted = set(d["qa_employee_ids"])
        for qid in wanted:
            proj.check_person(db, qid, "QA")
        current = set(db.scalars(select(TaskQAMember.employee_id).where(TaskQAMember.task_id == t.id)))
        for qid in current - wanted:
            db.query(TaskQAMember).filter(TaskQAMember.task_id == t.id, TaskQAMember.employee_id == qid).delete()
        for qid in wanted - current:
            db.add(TaskQAMember(task_id=t.id, employee_id=qid))
        primary_qa = sorted(wanted)[0] if wanted else None
        if t.qa_employee_id != primary_qa:
            t.qa_employee_id = primary_qa
        before["qa_members"], after["qa_members"] = sorted(current), sorted(wanted)

    for k, v in d.items():
        if k not in EDITABLE or k in ("company_id", "sub_head_employee_id", "head_employee_ids", "qa_employee_ids"):
            continue
        if k in ("head_employee_id", "qa_employee_id") and v is not None:
            from app.modules.tasks import projects as proj

            proj.check_person(db, v, "head" if k == "head_employee_id" else "QA")
        if k == "estimated_hours":
            old, new = round(t.estimated_seconds / 3600, 2), v
            if old != new:
                t.estimated_seconds = int(round(v * 3600))
                before[k], after[k] = old, new
            continue
        old = getattr(t, k)
        if old != v:
            setattr(t, k, v)
            before[k], after[k] = (str(old) if isinstance(old, date) else old), (str(v) if isinstance(v, date) else v)
    if after:
        t.version += 1
        _log(db, p, "TASK_UPDATED", t, before=before, after=after, request=request)
        from app.modules.tasks import projects as proj

        db.flush()
        proj.tell_head_and_qa(db, p, t, db.get(Project, t.project_id) if t.project_id else None, request,
                              only=tuple(w for k, w in (("head_employee_id", "head"), ("qa_employee_id", "qa")) if k in after))  # fmt: skip
        proj.resettle_task(db, p, t, request)


def reassign_task(db: Session, p: Principal, t: Task, new_assignee_id: int, reason: str | None, request: Request) -> None:
    if "owner" in p.roles or getattr(p, "is_owner", False):
        raise Forbidden("Owners do not transfer tasks")
    if not can_manage(p, t, "task.reassign"):
        raise Forbidden()
    if t.status not in OPEN_STATUSES:
        raise AppError("TASK_CLOSED", "Completed or cancelled tasks cannot be reassigned", 409)
    new = assert_assignable(db, p, db.get(Employee, new_assignee_id))
    if new.id == t.assignee_id:
        raise AppError("ALREADY_ASSIGNED", "The task already belongs to this person", 409)
    from app.modules.org import models as org_models
    new_cids = org_models.employee_company_ids(db, new)
    if new_cids is not None and getattr(t, "company_id", 1) not in new_cids:
        raise Forbidden(f"Assignee '{new.full_name}' does not belong to this task's company")
    now = clock.utcnow()
    old_id = t.assignee_id
    tq.close_running_for_task(db, t, "reassigned", now)  # the previous owner's timer stops at the hand-over
    for a in db.scalars(select(TaskAssignment).where(TaskAssignment.task_id == t.id, TaskAssignment.unassigned_at.is_(None))):
        a.unassigned_at = now
    assigned_by_id = p.employee.id if p.employee else t.assigned_by_id
    db.add(TaskAssignment(task_id=t.id, assignee_id=new.id, assigned_by_id=assigned_by_id, assigned_at=now, reason=reason))
    t.assignee_id, t.department_id, t.acknowledged_at = new.id, new.department_id, None
    if t.status == "blocked":  # the new owner inherits the blocked task; it returns to "assigned" once the blocker clears
        t.status_before_block = "assigned"
        t.version += 1
    elif t.status != "assigned":
        t.review_stage = None
        sm.force_status(db, t, "assigned", p.user.id, reason or "Reassigned")
    else:
        t.version += 1
    _log(db, p, "TASK_REASSIGNED", t, before={"assignee_id": old_id}, after={"assignee_id": new.id, "reason": reason}, request=request)


def change_priority(db: Session, p: Principal, t: Task, priority: str, reason: str | None, request: Request) -> None:
    if not can_manage(p, t, "task.priority.change"):
        raise Forbidden()
    if t.status not in OPEN_STATUSES:
        raise AppError("TASK_CLOSED", "Completed or cancelled tasks cannot be changed", 409)
    if priority not in PRIORITIES:
        raise AppError("INVALID_PRIORITY", "Unknown priority", 422)
    if priority == t.priority:
        return
    before = t.priority
    t.priority, t.priority_rank = priority, PRIORITY_RANK[priority]
    t.version += 1
    _log(db, p, "TASK_PRIORITY_CHANGED", t, before={"priority": before}, after={"priority": priority, "reason": reason}, request=request)


def cancel_task(db: Session, p: Principal, t: Task, reason: str, request: Request) -> None:
    if not is_leadership(p) or not can_manage(p, t, "task.cancel"):
        raise Forbidden("Only Owner and CEO have authority to cancel tasks")
    tq.close_running_for_task(db, t, "cancelled", clock.utcnow())  # a cancelled task stops the assignee's clock
    from app.modules.collab import blockers as blk  # imported here: collab builds on this module

    blk.close_all_for_task(db, t, p.user.id, "Task cancelled")  # ...and has no problems left to solve
    sm.transition(db, t, "cancelled", p.user.id, "manager", reason)
    t.review_stage = None
    t.cancelled_at, t.cancel_reason = clock.utcnow(), reason
    _log(db, p, "TASK_CANCELLED", t, after={"reason": reason}, request=request)
    if t.project_id:  # the project may now be fully done
        from app.modules.tasks import projects as proj

        db.flush()
        proj.check_ready(db, proj.get_project(db, t.project_id))


def acknowledge_task(db: Session, p: Principal, t: Task, request: Request) -> None:
    if p.employee is None or t.assignee_id != p.employee.id:
        raise Forbidden("Only the assignee can acknowledge this task")
    sm.transition(db, t, "acknowledged", p.user.id, "assignee")
    t.acknowledged_at = clock.utcnow()
    _log(db, p, "TASK_ACKNOWLEDGED", t, request=request)


# ------------------------------------------------------------------ queries


def list_tasks(db: Session, p: Principal, f: dict, page: int, page_size: int) -> dict:
    now = clock.utcnow()
    A, S = aliased(Employee), aliased(Employee)
    stmt = select(Task, A, S).join(A, A.id == Task.assignee_id).join(S, S.id == Task.assigned_by_id).where(visible_clause(p))
    if f.get("mine") and p.employee:
        stmt = stmt.where(Task.assignee_id == p.employee.id)
    for key, col in (("status", Task.status), ("priority", Task.priority), ("assignee_id", Task.assignee_id),
                     ("department_id", Task.department_id), ("project_id", Task.project_id), ("assigned_by_id", Task.assigned_by_id),
                     ("company_id", Task.company_id)):  # fmt: skip
        if f.get(key) not in (None, ""):
            stmt = stmt.where(col == f[key])
    if f.get("awaiting_my_review"):  # project/task work whose review turn is mine
        turns = []
        if p.employee:
            me = p.employee.id
            is_task_qa = Task.id.in_(select(TaskQAMember.task_id).where(TaskQAMember.employee_id == me))
            is_proj_qa = Task.project_id.in_(select(ProjectQAMember.project_id).where(ProjectQAMember.employee_id == me))
            is_dept_qa = Task.assignee_id.in_(select(Employee.id).where(Employee.department_id.in_(select(Department.id).where(Department.qa_employee_id == me))))
            turns.append(and_(Task.review_stage == "qa", Task.assignee_id != me, or_(Task.qa_employee_id == me, is_task_qa, is_proj_qa, is_dept_qa)))

            is_proj_head = Task.project_id.in_(select(Project.id).where(or_(Project.head_employee_id == me, Project.sub_head_employee_id == me)))
            is_dept_head = Task.assignee_id.in_(select(Employee.id).where(Employee.department_id.in_(select(Department.id).where(or_(Department.head_employee_id == me, Department.sub_head_employee_id == me)))))
            turns.append(and_(Task.review_stage == "head", Task.assignee_id != me, or_(Task.head_employee_id == me, Task.sub_head_employee_id == me, is_proj_head, is_dept_head)))

        if set(p.roles) & {"owner", "ceo"}:
            turns.append(Task.review_stage == "leadership")
        stmt = stmt.where(Task.status == "under_review", or_(*turns)) if turns else stmt.where(false())
    if f.get("overdue") is True:
        stmt = stmt.where(Task.due_at < late_cutoff(now), Task.status.notin_(TERMINAL))
    if f.get("open") is True:
        stmt = stmt.where(Task.status.in_(OPEN_STATUSES))
    if f.get("due_from"):
        stmt = stmt.where(Task.due_at >= cal.local_to_utc(db, datetime.combine(f["due_from"], time.min)))
    if f.get("due_to"):
        stmt = stmt.where(Task.due_at < cal.local_to_utc(db, datetime.combine(f["due_to"] + timedelta(days=1), time.min)))
    if f.get("q"):
        like = f"%{f['q'].strip()}%"
        stmt = stmt.where(or_(Task.title.like(like), Task.task_no.like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    closed = case((Task.status.in_(TERMINAL), 1), else_=0)
    overdue = case((and_(Task.due_at < late_cutoff(now), Task.status.notin_(TERMINAL)), 1), else_=0)
    # Priority engine: open before closed, overdue first, then priority, then earliest deadline.
    rows = db.execute(stmt.order_by(closed, overdue.desc(), Task.priority_rank, Task.due_at, Task.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()  # fmt: skip
    from app.modules.tasks import delays

    states = delays.states_for(db, [t for t, _a, _s in rows], now)
    items = [task_dict(db, t, a, s) | {"explanation_required": states[t.id]["required"], "escalation_level": states[t.id]["escalation_level"]}
             for t, a, s in rows]  # fmt: skip
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def timeline(db: Session, t: Task) -> list[dict]:
    rows = db.execute(
        select(ActivityLog, Employee.full_name)
        .outerjoin(Employee, Employee.user_id == ActivityLog.actor_user_id)
        .where(ActivityLog.task_id == t.id)
        .order_by(ActivityLog.id)
    ).all()
    return [{"id": a.id, "action": a.action, "actor": name, "before": a.before_json, "after": a.after_json,
             "at": z(a.created_at)} for a, name in rows]  # fmt: skip


def status_history(db: Session, t: Task) -> list[dict]:
    return [
        {"from": h.from_status, "to": h.to_status, "reason": h.reason, "at": z(h.created_at)}
        for h in db.scalars(select(TaskStatusHistory).where(TaskStatusHistory.task_id == t.id).order_by(TaskStatusHistory.id))
    ]


# ------------------------------------------------------------------ workload (who has how much)


def workload(db: Session, p: Principal, company_id: int | None = None) -> list[dict]:
    """People you can assign to, with their load (see _workload_rows)."""
    ids = p.scope_employee_ids("task.assign")
    q = select(Employee).where(Employee.status.in_(SELF_STATES), Employee.can_receive_tasks.is_(True))
    if ids is not None:
        peers = select(Employee.id).join(UserRole, UserRole.user_id == Employee.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code == "department_head") if "department_head" in p.roles else None
        q = q.where(Employee.id.in_(ids) | Employee.id.in_(peers)) if peers is not None else q.where(Employee.id.in_(ids))
    if company_id is not None:
        from app.modules.org.models import EmployeeCompany
        q = q.where(
            or_(
                Employee.company_id == company_id,
                Employee.company_id.is_(None),
                Employee.id.in_(select(EmployeeCompany.employee_id).where(EmployeeCompany.company_id == company_id)),
            )
        )
    elif p.company_ids() is not None:
        allowed_cids = p.company_ids()
        from app.modules.org.models import EmployeeCompany
        q = q.where(
            or_(
                Employee.company_id.in_(allowed_cids),
                Employee.company_id.is_(None),
                Employee.id.in_(select(EmployeeCompany.employee_id).where(EmployeeCompany.company_id.in_(allowed_cids))),
            )
        )
    return _workload_rows(db, p, db.scalars(q).all())


def my_workload(db: Session, p: Principal) -> dict | None:
    """The signed-in employee's own load (for their dashboard)."""
    if p.employee is None:
        return None
    rows = _workload_rows(db, p, [p.employee])
    return rows[0] if rows else None


def _workload_rows(db: Session, p: Principal, people: list[Employee]) -> list[dict]:
    """Per person: open tasks by status/priority, overdue, hours, and load vs. next-7-working-days capacity.
    Load counts what is LEFT to do (estimate minus time already worked), not the full estimate."""
    now = clock.utcnow()
    if not people:
        return []
    pid = [e.id for e in people]
    open_rows = db.execute(
        select(Task.id, Task.assignee_id, Task.status, Task.priority, Task.due_at, Task.estimated_seconds)
        .where(Task.assignee_id.in_(pid), Task.status.in_(OPEN_STATUSES))
    ).all()  # fmt: skip
    worked = tq.active_seconds_map(db, [r.id for r in open_rows], now)

    today = cal.utc_to_local(db, now).date()
    horizon_utc = cal.local_to_utc(db, datetime.combine(today + timedelta(days=7), time.min))
    working_days = [d for d in (today + timedelta(days=i) for i in range(7)) if cal.is_working_day(db, d)]
    from app.modules.workcal.models import EmployeeLeave

    leaves = db.scalars(select(EmployeeLeave).where(EmployeeLeave.employee_id.in_(pid), EmployeeLeave.status == "approved",
                                                    EmployeeLeave.to_date >= today, EmployeeLeave.from_date <= today + timedelta(days=6))).all()  # fmt: skip
    depts = {d.id: d.name for d in db.scalars(select(Department))}
    out = []
    for e in people:
        mine = [r for r in open_rows if r.assignee_id == e.id]
        by_status = {s: 0 for s in OPEN_STATUSES}
        by_priority = {pr: 0 for pr in PRIORITIES}
        overdue = due7 = 0
        hours_all = hours7 = remaining_all = 0.0
        for r in mine:
            by_status[r.status] += 1
            by_priority[r.priority] += 1
            hours_all += r.estimated_seconds / 3600
            h = max(0, r.estimated_seconds - worked.get(r.id, 0)) / 3600  # what is still left to do
            remaining_all += h
            if r.due_at < late_cutoff(now):
                overdue += 1
            if r.due_at < horizon_utc:  # overdue + due within the next 7 days
                due7 += 1
                hours7 += h
        my_leaves = [lv for lv in leaves if lv.employee_id == e.id]
        capacity = sum(float(e.daily_capacity_hours) for d in working_days if not any(lv.from_date <= d <= lv.to_date for lv in my_leaves))
        pct = (hours7 / capacity * 100) if capacity else (999.0 if hours7 else 0.0)
        level = "normal" if pct <= 80 else "high" if pct <= 100 else "overloaded"
        out.append({
            "employee_id": e.id, "full_name": e.full_name, "job_title": e.job_title, "department_id": e.department_id,
            "department": depts.get(e.department_id), "on_leave": e.status == "on_leave",
            "is_me": bool(p.employee and p.employee.id == e.id),
            "open_tasks": len(mine), "overdue_tasks": overdue, "due_next_7_days": due7,
            "by_status": by_status, "by_priority": by_priority,
            "open_estimated_hours": round(hours_all, 1), "open_remaining_hours": round(remaining_all, 1),
            "next7_estimated_hours": round(hours7, 1),
            "capacity_hours_next_7_days": round(capacity, 1), "load_pct": round(pct, 0), "level": level,
        })  # fmt: skip
    return sorted(out, key=lambda r: (-r["open_tasks"], r["full_name"]))
