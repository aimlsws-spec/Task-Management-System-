"""Projects (ADR 003): expected result, head, team, points added any time, and the review chain's project-level rules.
Routers stay thin; the rules live here. Authorization = `project.manage` (create/edit) and, for sign-off, the Owner/CEO role."""

import re

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.modules.audit import service as audit
from app.modules.notifications import outbox
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import loop
from app.modules.tasks.models import Project, ProjectMember, ProjectPoint, Task
from app.modules.workcal import service as cal

LEADERSHIP_ROLES = {"owner", "ceo"}
EDITABLE_STATUS = ("active", "on_hold", "archived")


def is_leadership(p: Principal) -> bool:
    """Owner or CEO (the two who sign off). Role-based on purpose: the Admin outranks them but signs nothing off."""
    return bool(set(p.roles) & LEADERSHIP_ROLES)


def _me(p: Principal) -> int:
    return p.employee.id if p.employee else -1


def _z(dt):
    return dt.isoformat() + "Z" if dt else None


# ---------------------------------------------------------------- reading


def get_project(db: Session, project_id: int) -> Project:
    pr = db.get(Project, project_id)
    if pr is None:
        raise NotFound("Project")
    return pr


def team_ids(db: Session, pr: Project) -> set[int]:
    return set(db.scalars(select(ProjectMember.employee_id).where(ProjectMember.project_id == pr.id)))


def can_view(db: Session, p: Principal, pr: Project) -> bool:
    me = _me(p)
    if p.has("project.manage") or me in (pr.assignee_id, pr.head_employee_id, pr.qa_employee_id) or me in team_ids(db, pr):
        return True
    return db.scalar(select(Task.id).where(Task.project_id == pr.id, or_(Task.assignee_id == me, Task.assigned_by_id == me)).limit(1)) is not None


def visible_project(db: Session, p: Principal, project_id: int) -> Project:
    pr = db.get(Project, project_id)
    if pr is None or not can_view(db, p, pr):
        raise NotFound("Project")  # not involved == does not exist
    return pr


def _person(db: Session, emp_id: int | None) -> dict | None:
    e = db.get(Employee, emp_id) if emp_id else None
    return None if e is None else {"id": e.id, "full_name": e.full_name, "job_title": e.job_title, "department_id": e.department_id}


def _point_status(point: ProjectPoint, task: Task | None) -> str:
    if point.is_done:
        return "done"
    if point.task_id is None or task is None:
        return "open"
    return {"completed": "done", "cancelled": "cancelled"}.get(task.status, "assigned")


def counts(db: Session, pr: Project) -> dict:
    points = db.scalars(select(ProjectPoint).where(ProjectPoint.project_id == pr.id)).all()
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.project_id == pr.id))}
    open_points = sum(1 for x in points if _point_status(x, tasks.get(x.task_id)) == "open")
    done_points = sum(1 for x in points if _point_status(x, tasks.get(x.task_id)) == "done")
    live = [t for t in tasks.values() if t.status != "cancelled"]
    done = [t for t in live if t.status == "completed"]
    return {
        "points": len(points), "open_points": open_points, "done_points": done_points, "tasks": len(live), "done_tasks": len(done),
        "awaiting_review": sum(1 for t in live if t.status == "under_review"),
        "ready_for_review": pr.status == "active" and open_points == 0 and ((bool(live) and len(done) == len(live)) or (not live and bool(points) and done_points == len(points))),
    }  # fmt: skip


def summary(db: Session, pr: Project) -> dict:
    c = counts(db, pr)
    return {
        "id": pr.id, "code": pr.code, "name": pr.name, "description": pr.description, "status": pr.status,
        "expected_result": pr.expected_result, "head": _person(db, pr.head_employee_id), "qa": _person(db, pr.qa_employee_id),
        "assignee": _person(db, pr.assignee_id), "progress_pct": pr.progress_pct,
        "department_id": pr.department_id,
        "starts_on": pr.starts_on.isoformat() if pr.starts_on else None, "ends_on": pr.ends_on.isoformat() if pr.ends_on else None,
        "counts": c, "ready_for_review": c["ready_for_review"],
    }  # fmt: skip


def list_projects(db: Session, p: Principal) -> list[dict]:
    return [summary(db, pr) for pr in db.scalars(select(Project).order_by(Project.name)) if can_view(db, p, pr)]


def detail(db: Session, p: Principal, pr: Project) -> dict:
    from app.modules.tasks import service

    tasks = service.list_tasks(db, p, {"project_id": pr.id}, 1, 100)["items"]
    by_id = {t["id"]: t for t in tasks}
    out = summary(db, pr)
    points = []
    for x in db.scalars(select(ProjectPoint).where(ProjectPoint.project_id == pr.id).order_by(ProjectPoint.position, ProjectPoint.id)):
        task = db.get(Task, x.task_id) if x.task_id else None
        t = by_id.get(x.task_id)
        points.append({
            "id": x.id, "title": x.title, "details": x.details, "expected_result": x.expected_result, "position": x.position,
            "is_done": x.is_done,
            "status": _point_status(x, task),
            "task": ({"id": t["id"], "task_no": t["task_no"], "status": t["status"], "assignee": t["assignee"], "due_at": t["due_at"],
                      "review_stage": t.get("review_stage")} if t else None),
        })  # fmt: skip
    members = [_person(db, i) for i in sorted(team_ids(db, pr))]
    reviewer = db.scalar(select(Employee.full_name).where(Employee.user_id == pr.reviewed_by_user_id)) if pr.reviewed_by_user_id else None
    return out | {
        "members": members, "points": points, "tasks": tasks, "completed_at": _z(pr.completed_at), "review_note": pr.review_note,
        "reviewed_by": reviewer, "created_at": _z(pr.created_at),
        "can_manage": p.has("project.manage"), "can_complete": is_leadership(p) and p.has("project.manage"),
    }  # fmt: skip


# ---------------------------------------------------------------- helpers


def _code_for(db: Session, name: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")[:20] or "PROJECT"
    code, n = base, 1
    while db.scalar(select(Project.id).where(Project.code == code)):
        n += 1
        code = f"{base}-{n}"
    return code


def check_person(db: Session, emp_id: int, what: str) -> Employee:
    e = db.get(Employee, emp_id)
    if e is None or e.status == "inactive":
        raise AppError("INVALID_EMPLOYEE", f"The {what} must be an active employee", 422)
    return e


_employee = check_person


def _tell(db: Session, p: Principal, event: str, pr: Project, emp: Employee) -> None:
    """One person is told about the project (head named / added to the team)."""
    outbox.emit(db, event, None, p.user.id, {"after": {"project_id": pr.id, "project": pr.name, "user_id": emp.user_id, **_facts(pr)}})


def _facts(pr: Project) -> dict:
    """What a person added to a project needs to know at once: the deadline and the expected result."""
    return {"starts_on": pr.starts_on.isoformat() if pr.starts_on else "", "ends_on": pr.ends_on.isoformat() if pr.ends_on else "",
            "expected_result": (pr.expected_result or "")[:1000]}


def _set_members(db: Session, p: Principal, pr: Project, ids: list[int]) -> None:
    wanted = {i for i in ids}
    for i in wanted:
        _employee(db, i, "team member")
    have = team_ids(db, pr)
    for i in have - wanted:
        db.query(ProjectMember).filter(ProjectMember.project_id == pr.id, ProjectMember.employee_id == i).delete()
    for i in sorted(wanted - have):
        db.add(ProjectMember(project_id=pr.id, employee_id=i))
        _tell(db, p, "PROJECT_MEMBER_ADDED", pr, db.get(Employee, i))
    db.flush()


def _set_head(db: Session, p: Principal, pr: Project, head_id: int | None, request: Request | None) -> None:
    if head_id == pr.head_employee_id:
        return
    head = _employee(db, head_id, "project head") if head_id is not None else None
    pr.head_employee_id = head_id
    db.flush()
    if head is not None:
        _tell(db, p, "PROJECT_HEAD_NAMED", pr, head)
    resettle_reviews(db, p, pr, request)


def _set_qa(db: Session, p: Principal, pr: Project, qa_id: int | None, request: Request | None) -> None:
    if qa_id == pr.qa_employee_id:
        return
    qa = _employee(db, qa_id, "QA") if qa_id is not None else None
    pr.qa_employee_id = qa_id
    db.flush()
    if qa is not None:
        _tell(db, p, "PROJECT_QA_NAMED", pr, qa)
    resettle_reviews(db, p, pr, request)


def resettle_reviews(db: Session, p: Principal, pr: Project, request: Request | None) -> None:
    """Finished work waiting at a stage that no longer has anyone (head/QA removed) moves on to the next stage."""
    for t in db.scalars(select(Task).where(Task.project_id == pr.id, Task.status == "under_review", Task.review_stage.isnot(None))):
        resettle_task(db, p, t, request)


def resettle_task(db: Session, p: Principal, t: Task, request: Request | None) -> None:
    if t.status != "under_review" or t.review_stage is None or t.review_stage in loop.stages(db, t):
        return
    t.review_stage = loop.next_stage(db, t, t.review_stage)
    t.version += 1
    announce_stage(db, p, t, request)


def reopen_if_completed(db: Session, p: Principal, pr: Project, why: str, request: Request | None) -> None:
    """New work in a completed project puts it back to active: it is not finished any more."""
    if pr.status == "completed":
        pr.status, pr.completed_at, pr.reviewed_by_user_id, pr.review_note = "active", None, None, None
        audit.log(db, p.user.id, "PROJECT_REOPENED", "project", pr.id, after={"why": why}, request=request)


# ---------------------------------------------------------------- create / update


def create_project(db: Session, p: Principal, d: dict, request: Request) -> Project:
    name = d["name"].strip()
    code = (d.get("code") or "").upper() or _code_for(db, name)
    if db.scalar(select(Project.id).where(Project.code == code)):
        raise Conflict("PROJECT_EXISTS", "A project with this code already exists")
    s, e = d.get("starts_on"), d.get("ends_on")
    if e is None:
        raise AppError("DEADLINE_REQUIRED", "A project needs a deadline (end date)", 422)
    if e < cal.utc_to_local(db, clock.utcnow()).date():
        raise AppError("PAST_DEADLINE", "The project deadline cannot be in the past", 422)
    if s and e < s:
        raise AppError("INVALID_DATES", "End date cannot be before start date", 422)

    head_id = d.get("head_employee_id")
    assignee_id = d.get("assignee_id")
    member_ids = d.get("member_ids") or []
    department_id = d.get("department_id")

    if head_id is None:
        from app.modules.org.models import Department
        target_emp = None
        if assignee_id:
            target_emp = db.get(Employee, assignee_id)
        if not target_emp and member_ids:
            target_emp = db.get(Employee, member_ids[0])
        dept_id = target_emp.department_id if target_emp else department_id
        if dept_id:
            dept = db.get(Department, dept_id)
            if dept and dept.head_employee_id:
                head_id = dept.head_employee_id

    pr = Project(code=code, name=name, description=d.get("description"), expected_result=d.get("expected_result"),
                 department_id=department_id, starts_on=s, ends_on=e, owner_employee_id=p.employee.id if p.employee else None,
                 assignee_id=assignee_id, progress_pct=0)
    db.add(pr)
    db.flush()
    _set_head(db, p, pr, head_id, request)
    _set_qa(db, p, pr, d.get("qa_employee_id"), request)
    _set_members(db, p, pr, member_ids)
    for pt in d.get("points") or []:
        _new_point(db, p, pr, pt)
    outbox.emit(db, "PROJECT_CREATED", None, p.user.id, {"after": {
        "project_id": pr.id, "project": pr.name, **_facts(pr), "head": _name(db, pr.head_employee_id), "qa": _name(db, pr.qa_employee_id),
        "team": ", ".join(_name(db, i) for i in sorted(team_ids(db, pr)))}})
    audit.log(db, p.user.id, "PROJECT_CREATED", "project", pr.id,
              after={"code": pr.code, "name": pr.name, "assignee_id": pr.assignee_id, "head_employee_id": pr.head_employee_id, "qa_employee_id": pr.qa_employee_id, "points": len(d.get("points") or [])}, request=request)  # fmt: skip
    return pr


def _name(db: Session, emp_id: int | None) -> str:
    e = db.get(Employee, emp_id) if emp_id else None
    return e.full_name if e else ""


def update_project(db: Session, p: Principal, pr: Project, d: dict, request: Request) -> None:
    if "ends_on" in d and d["ends_on"] is None:
        raise AppError("DEADLINE_REQUIRED", "A project needs a deadline (end date)", 422)
    before, after = {}, {}
    for k in ("name", "description", "expected_result", "starts_on", "ends_on"):
        if k in d and getattr(pr, k) != d[k]:
            before[k], after[k] = str(getattr(pr, k)), str(d[k])
            setattr(pr, k, d[k])
    if "status" in d and d["status"] != pr.status:
        if pr.status == "completed" and d["status"] == "active":
            reopen_if_completed(db, p, pr, "reopened by hand", request)
        elif pr.status == "completed":
            raise Conflict("PROJECT_COMPLETED", "A completed project can only be reopened (set it to active)")
        else:
            before["status"], after["status"] = pr.status, d["status"]
            pr.status = d["status"]
    if pr.starts_on and pr.ends_on and pr.ends_on < pr.starts_on:
        raise AppError("INVALID_DATES", "End date cannot be before start date", 422)
    if "head_employee_id" in d:
        before["head_employee_id"], after["head_employee_id"] = pr.head_employee_id, d["head_employee_id"]
        _set_head(db, p, pr, d["head_employee_id"], request)
    if "qa_employee_id" in d:
        before["qa_employee_id"], after["qa_employee_id"] = pr.qa_employee_id, d["qa_employee_id"]
        _set_qa(db, p, pr, d["qa_employee_id"], request)
    if "member_ids" in d and d["member_ids"] is not None:
        before["members"], after["members"] = sorted(team_ids(db, pr)), sorted(d["member_ids"])
        _set_members(db, p, pr, d["member_ids"])
    if "assignee_id" in d and d["assignee_id"] != pr.assignee_id:
        before["assignee_id"], after["assignee_id"] = pr.assignee_id, d["assignee_id"]
        pr.assignee_id = d["assignee_id"]
    if "progress_pct" in d and d["progress_pct"] != pr.progress_pct:
        before["progress_pct"], after["progress_pct"] = pr.progress_pct, d["progress_pct"]
        pr.progress_pct = d["progress_pct"]
    if after:
        audit.log(db, p.user.id, "PROJECT_UPDATED", "project", pr.id, before=before, after=after, request=request)
    if after:
        audit.log(db, p.user.id, "PROJECT_UPDATED", "project", pr.id, before=before, after=after, request=request)


# ---------------------------------------------------------------- points


def _new_point(db: Session, p: Principal, pr: Project, d: dict) -> ProjectPoint:
    title = (d.get("title") or "").strip()
    if len(title) < 2:
        raise AppError("TITLE_REQUIRED", "Give the point a short title", 422)
    pos = (db.scalar(select(func.max(ProjectPoint.position)).where(ProjectPoint.project_id == pr.id)) or 0) + 1
    pt = ProjectPoint(project_id=pr.id, title=title[:200], details=(d.get("details") or "").strip() or None,
                      expected_result=(d.get("expected_result") or "").strip() or None, position=pos, created_by_user_id=p.user.id)  # fmt: skip
    db.add(pt)
    db.flush()
    return pt


def point_dict(db: Session, x: ProjectPoint) -> dict:
    task = db.get(Task, x.task_id) if x.task_id else None
    return {"id": x.id, "title": x.title, "details": x.details, "expected_result": x.expected_result, "status": _point_status(x, task),
            "is_done": x.is_done, "task_id": x.task_id}  # fmt: skip


def toggle_point(db: Session, p: Principal, pr: Project, point_id: int, request: Request | None) -> ProjectPoint:
    x = _point(db, pr, point_id)
    x.is_done = not x.is_done
    db.flush()
    audit.log(db, p.user.id, "PROJECT_POINT_TOGGLED", "project", pr.id, after={"point_id": x.id, "is_done": x.is_done}, request=request)
    check_ready(db, pr)
    return x


def _point(db: Session, pr: Project, point_id: int) -> ProjectPoint:
    x = db.get(ProjectPoint, point_id)
    if x is None or x.project_id != pr.id:
        raise NotFound("Point")
    return x


def add_point(db: Session, p: Principal, pr: Project, d: dict, request: Request) -> ProjectPoint:
    if pr.status == "archived":
        raise Conflict("PROJECT_ARCHIVED", "Reactivate the project before adding to it")
    pt = _new_point(db, p, pr, d)
    reopen_if_completed(db, p, pr, "a new point was added", request)
    audit.log(db, p.user.id, "PROJECT_POINT_ADDED", "project", pr.id, after={"point_id": pt.id, "title": pt.title}, request=request)
    return pt


def _assignable_state(db: Session, x: ProjectPoint) -> bool:
    task = db.get(Task, x.task_id) if x.task_id else None
    return x.task_id is None or task is None or task.status == "cancelled"


def update_point(db: Session, p: Principal, pr: Project, point_id: int, d: dict, request: Request) -> ProjectPoint:
    x = _point(db, pr, point_id)
    if not _assignable_state(db, x):
        raise Conflict("POINT_ASSIGNED", "This point is already a task. Edit the task instead.")
    for k in ("title", "details", "expected_result"):
        if k in d:
            v = (d[k] or "").strip() or None
            if k == "title" and (v is None or len(v) < 2):
                raise AppError("TITLE_REQUIRED", "Give the point a short title", 422)
            setattr(x, k, v)
    db.flush()
    audit.log(db, p.user.id, "PROJECT_POINT_UPDATED", "project", pr.id, after={"point_id": x.id, **{k: d[k] for k in d}}, request=request)
    return x


def delete_point(db: Session, p: Principal, pr: Project, point_id: int, request: Request) -> None:
    x = _point(db, pr, point_id)
    if not _assignable_state(db, x):
        raise Conflict("POINT_ASSIGNED", "This point is already a task and cannot be removed")
    audit.log(db, p.user.id, "PROJECT_POINT_REMOVED", "project", pr.id, before={"point_id": x.id, "title": x.title}, request=request)
    db.delete(x)
    db.flush()
    check_ready(db, pr)


def assign_point(db: Session, p: Principal, pr: Project, point_id: int, d: dict, request: Request):
    from app.modules.tasks import service

    x = _point(db, pr, point_id)
    if not _assignable_state(db, x):
        raise Conflict("POINT_ASSIGNED", "This point has already been assigned")
    body = {
        "title": x.title, "description": "\n\n".join(s for s in (x.details, f"Expected result: {x.expected_result}" if x.expected_result else None) if s) or x.title,
        "instructions": d.get("instructions"), "assignee_id": d["assignee_id"], "priority": d["priority"], "due_date": d["due_date"],
        "head_employee_id": d.get("head_employee_id"), "qa_employee_id": d.get("qa_employee_id"), "start_date": d.get("start_date"), "estimated_hours": d.get("estimated_hours"), "project_id": pr.id,
        "category_id": d.get("category_id"), "type_id": d.get("type_id"),
    }  # fmt: skip
    task, warnings = service.create_task(db, p, body, request)
    x.task_id = task.id
    db.flush()
    return task, x, warnings


# ---------------------------------------------------------------- the team rule, hooks used by tasks


def assert_can_take_task(db: Session, project_id: int, assignee_id: int) -> Project:
    """Called by task creation. With a team, only members (and the head) may receive tasks in the project."""
    pr = get_project(db, project_id)
    if pr.status in ("archived", "on_hold"):
        raise AppError("PROJECT_NOT_ACTIVE", f"This project is {pr.status.replace('_', ' ')}; reactivate it first", 409)
    team = team_ids(db, pr)
    if team and assignee_id not in team and assignee_id != pr.head_employee_id:
        raise AppError("NOT_ON_PROJECT_TEAM", "This project has a team. Add the person to the project first, or pick a team member.", 422)
    return pr


def on_task_created(db: Session, p: Principal, t: Task, pr: Project | None, request: Request | None) -> None:
    """The head and the QA are told about every task created for them; new work reopens a completed project."""
    if pr is not None:
        reopen_if_completed(db, p, pr, "a task was added", request)
    tell_head_and_qa(db, p, t, pr, request)


def tell_head_and_qa(db: Session, p: Principal, t: Task, pr: Project | None, request: Request | None, only: tuple[str, ...] = ("head", "qa")) -> None:
    after = {"project": pr.name if pr else "", "project_id": pr.id if pr else None}
    head, qa = loop.named_head_id(db, t), loop.named_qa_id(db, t)  # only people somebody chose; a department head hears via the normal task rules
    if pr and "head" in only and head and head != t.assignee_id:
        audit.log(db, p.user.id, "PROJECT_TASK_ASSIGNED", "task", t.id, after=after, request=request, task_id=t.id)
    if "qa" in only and qa and qa != t.assignee_id:
        audit.log(db, p.user.id, "TASK_QA_ASSIGNED", "task", t.id, after=after, request=request, task_id=t.id)


def announce_stage(db: Session, p: Principal, t: Task, request: Request | None) -> None:
    """Tell whoever's turn it is that finished work is waiting for them."""
    pr = db.get(Project, t.project_id) if t.project_id else None
    action = {"qa": "TASK_QA_REVIEW_NEEDED", "head": "TASK_HEAD_REVIEW_NEEDED"}.get(t.review_stage, "TASK_LEADERSHIP_REVIEW_NEEDED")
    audit.log(db, p.user.id, action, "task", t.id, after={"project": pr.name if pr else "", "project_id": pr.id if pr else None}, request=request, task_id=t.id)


def my_turn_to_review(db: Session, p: Principal, t: Task) -> bool:
    if t.status != "under_review" or not t.review_stage:
        return False
    if t.review_stage in ("qa", "head"):
        who = loop.qa_id(db, t) if t.review_stage == "qa" else loop.head_id(db, t)
        return bool(p.employee and who == p.employee.id and t.assignee_id != p.employee.id)
    return is_leadership(p) and not (p.employee and p.employee.id == t.assignee_id and p.rank < 100)


def first_stage(db: Session, t: Task) -> str:
    """Where finished work goes first: QA if there is one, else the head, else leadership (nobody reviews their own work)."""
    return loop.first_stage(db, t)


def check_ready(db: Session, pr: Project) -> None:
    """When the last piece of work is signed off, tell the Owner and CEO the project is ready for their review (once)."""
    c = counts(db, pr)
    if c["ready_for_review"]:
        outbox.emit(db, "PROJECT_READY_FOR_REVIEW", None, None, {"after": {"project_id": pr.id, "project": pr.name}},
                    dedupe_key=f"PROJECT_READY:{pr.id}:{c['done_tasks']}")  # fmt: skip


def complete_project(db: Session, p: Principal, project_id: int, note: str | None, request: Request) -> Project:
    if not is_leadership(p):
        raise Forbidden("Only the Owner or CEO can mark a project completed")
    pr = get_project(db, project_id)
    if pr.status == "completed":
        raise Conflict("ALREADY_COMPLETED", "This project is already completed")
    if not counts(db, pr)["ready_for_review"]:
        raise Conflict("PROJECT_NOT_READY", "Every point must be assigned and every task completed (or cancelled) first")
    pr.status, pr.completed_at, pr.reviewed_by_user_id, pr.review_note = "completed", clock.utcnow(), p.user.id, (note or "").strip() or None
    audit.log(db, p.user.id, "PROJECT_COMPLETED", "project", pr.id, after={"note": pr.review_note}, request=request)
    outbox.emit(db, "PROJECT_COMPLETED", None, p.user.id, {"after": {"project_id": pr.id, "project": pr.name}})
    return pr
