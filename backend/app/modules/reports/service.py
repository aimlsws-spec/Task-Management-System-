"""Phase 8: dashboards and reports. Every number is computed from raw task / time / blocker rows inside the caller's
scope (the same scope as task.view), so a Department Head can never see another department.

Completion, on-time, ACTIVE hours and ELAPSED time are reported separately and never merged into one "score" (FR-110).
Delay explanations follow the same release rule as the task screens: CEO / Owner only count what the line approved."""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.grace import late_cutoff
from app.modules.collab.models import OPEN_BLOCKER, TaskBlocker
from app.modules.org.models import Department, Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import delays
from app.modules.tasks.models import OPEN_STATUSES, STATUSES, Task, TaskDeadlineHistory
from app.modules.tasks.service import visible_clause, z
from app.modules.timetracking import queries as tq

REPORTS = {
    "completion": "Completed work: how many tasks finished, on time or late",
    "on_time": "On-time delivery against the current and the original deadline",
    "overdue": "Overdue tasks and the state of their delay explanations",
    "extensions": "How often deadlines moved, and why",
    "time": "Active hours worked versus estimate and elapsed time",
    "rework": "Reverted and reopened work",
    "blockers": "Blockers raised and how long they waited",
    "workload": "Open load per person against capacity",
}


def parse_range(date_from, date_to) -> tuple[datetime | None, datetime | None]:
    lo = datetime.combine(date_from, datetime.min.time()) if date_from else None
    hi = datetime.combine(date_to, datetime.min.time()) + timedelta(days=1) if date_to else None
    return lo, hi


def _tasks(db: Session, p: Principal, f: dict, *extra) -> list[Task]:
    q = select(Task).where(visible_clause(p), *extra)
    if f.get("department_id"):
        q = q.where(Task.department_id == f["department_id"])
    if f.get("assignee_id"):
        q = q.where(Task.assignee_id == f["assignee_id"])
    if f.get("priority"):
        q = q.where(Task.priority == f["priority"])
    return list(db.scalars(q))


def _names(db: Session) -> tuple[dict[int, str], dict[int, str]]:
    emps = {e.id: e.full_name for e in db.scalars(select(Employee))}
    depts = {d.id: d.name for d in db.scalars(select(Department))}
    return emps, depts


def _hours(sec: float) -> float:
    return round(sec / 3600, 2)


def _pct(a: int, b: int) -> float | None:
    return round(a * 100 / b, 1) if b else None


def _range_extra(f: dict, column) -> list:
    lo, hi = parse_range(f.get("date_from"), f.get("date_to"))
    out = []
    if lo:
        out.append(column >= lo)
    if hi:
        out.append(column < hi)
    return out


# ---------------------------------------------------------------- dashboard


def dashboard(db: Session, p: Principal) -> dict:
    """One summary for whoever is looking; its breadth is their scope (Owner/CEO: company, Manager: team, Head: department)."""
    now = clock.utcnow()
    scope = p.scope("task.view")
    label = {"organization": "Whole organization", "team": "Your team", "department": "Your department", "self": "You"}.get(scope, "You")
    tasks = _tasks(db, p, {})
    emps, depts = _names(db)
    open_t = [t for t in tasks if t.status in OPEN_STATUSES]
    by_status = {s: 0 for s in STATUSES}
    for t in tasks:
        by_status[t.status] += 1
    overdue_t = [t for t in open_t if t.due_at < late_cutoff(now)]
    soon = [t for t in open_t if now <= t.due_at < now + timedelta(days=7)]
    week_ago = now - timedelta(days=7)
    done_week = [t for t in tasks if t.status == "completed" and t.completed_at and t.completed_at >= week_ago]
    finished = [t for t in tasks if t.status == "completed" and t.completed_at]
    on_time_t = [t for t in finished if t.completed_at <= t.due_at]
    ids = [t.id for t in tasks]
    open_blockers = db.scalar(select(func.count()).select_from(TaskBlocker).where(TaskBlocker.task_id.in_(ids or [0]), TaskBlocker.status.in_(OPEN_BLOCKER))) or 0
    states = delays.states_for(db, overdue_t, now)
    leadership = delays.is_leadership(p)
    dept_rows = []
    for did in sorted({t.department_id for t in tasks}):
        dt = [t for t in tasks if t.department_id == did]
        do = [t for t in dt if t.status in OPEN_STATUSES]
        df = [t for t in dt if t.status == "completed" and t.completed_at]
        dept_rows.append({"department_id": did, "department": depts.get(did), "open": len(do), "overdue": sum(1 for t in do if t.due_at < late_cutoff(now)),
                          "completed": len(df), "on_time_pct": _pct(sum(1 for t in df if t.completed_at <= t.due_at), len(df))})  # fmt: skip
    people: dict[int, dict] = defaultdict(lambda: {"open": 0, "overdue": 0, "completed": 0})
    for t in tasks:
        row = people[t.assignee_id]
        if t.status in OPEN_STATUSES:
            row["open"] += 1
            row["overdue"] += 1 if t.due_at < late_cutoff(now) else 0
        elif t.status == "completed":
            row["completed"] += 1
    top_overdue = sorted(overdue_t, key=lambda t: (t.priority_rank, t.due_at))[:8]
    out = {
        "scope": scope, "scope_label": label, "generated_at": z(now),
        "totals": {"all": len(tasks), "open": len(open_t), "overdue": len(overdue_t), "due_next_7_days": len(soon),
                   "completed_last_7_days": len(done_week), "completed_total": len(finished), "open_blockers": open_blockers,
                   "on_time_pct": _pct(len(on_time_t), len(finished))},  # fmt: skip
        "by_status": by_status,
        "by_priority": {pr: sum(1 for t in open_t if t.priority == pr) for pr in ("critical", "high", "medium", "low")},
        "by_department": dept_rows,
        "by_person": sorted(({"employee_id": e, "full_name": emps.get(e)} | v for e, v in people.items()), key=lambda r: (-r["overdue"], -r["open"]))[:15],
        "top_overdue": [{"task_id": t.id, "task_no": t.task_no, "title": t.title, "assignee": emps.get(t.assignee_id), "priority": t.priority,
                         "due_at": z(t.due_at), "extension_count": t.extension_count, "explanation_required": states[t.id]["required"]} for t in top_overdue],  # fmt: skip
    }
    if p.has("delay.review"):  # what needs a decision from me (leadership: only what was escalated to them)
        q = delays.queue(db, p)
        out["needs_my_decision"] = {"explanations": len(q["awaiting"]), "overdue_without_reason": 0 if leadership else len(q["missing"])}
    return out


# ---------------------------------------------------------------- reports


def run(db: Session, p: Principal, name: str, f: dict) -> dict:
    fn = {"completion": completion, "on_time": on_time, "overdue": overdue, "extensions": extensions, "time": time_report,
          "rework": rework, "blockers": blockers, "workload": workload}[name]  # fmt: skip
    columns, rows, summary = fn(db, p, f)
    return {"name": name, "title": REPORTS[name], "columns": columns, "rows": rows, "summary": summary, "generated_at": z(clock.utcnow())}


def completion(db, p, f):
    tasks = _tasks(db, p, f, Task.status == "completed", Task.completed_at.is_not(None), *_range_extra(f, Task.completed_at))
    emps, depts = _names(db)
    g: dict[int, dict] = defaultdict(lambda: {"completed": 0, "on_time": 0, "late": 0, "dept": None})
    for t in tasks:
        r = g[t.assignee_id]
        r["dept"] = t.department_id
        r["completed"] += 1
        r["on_time" if t.completed_at <= t.due_at else "late"] += 1
    rows = [{"employee": emps.get(e), "department": depts.get(v["dept"]), "completed": v["completed"], "on_time": v["on_time"], "late": v["late"],
             "on_time_pct": _pct(v["on_time"], v["completed"])} for e, v in g.items()]  # fmt: skip
    rows.sort(key=lambda r: -r["completed"])
    return (["employee", "department", "completed", "on_time", "late", "on_time_pct"], rows,
            {"completed": len(tasks), "on_time": sum(r["on_time"] for r in rows), "late": sum(r["late"] for r in rows)})  # fmt: skip


ON_TIME_COLS = ["task_no", "title", "employee", "department", "priority", "original_due", "current_due", "completed_at", "extensions",
                "on_time_vs_current", "on_time_vs_original"]  # fmt: skip


def on_time(db, p, f):
    tasks = _tasks(db, p, f, Task.status == "completed", Task.completed_at.is_not(None), *_range_extra(f, Task.completed_at))
    emps, depts = _names(db)
    rows = [{"task_no": t.task_no, "title": t.title, "employee": emps.get(t.assignee_id), "department": depts.get(t.department_id), "priority": t.priority,
             "original_due": z(t.original_due_at), "current_due": z(t.due_at), "completed_at": z(t.completed_at), "extensions": t.extension_count,
             "on_time_vs_current": t.completed_at <= t.due_at, "on_time_vs_original": t.completed_at <= t.original_due_at} for t in tasks]  # fmt: skip
    return (ON_TIME_COLS, rows,
            {"tasks": len(rows), "on_time_vs_current_pct": _pct(sum(r["on_time_vs_current"] for r in rows), len(rows)),
             "on_time_vs_original_pct": _pct(sum(r["on_time_vs_original"] for r in rows), len(rows))})  # fmt: skip


def overdue(db, p, f):
    now = clock.utcnow()
    tasks = _tasks(db, p, f, Task.status.in_(delays.REQUIRED_STATUSES), Task.due_at < late_cutoff(now))
    states = delays.states_for(db, tasks, now)
    emps, depts = _names(db)
    leadership = delays.is_leadership(p)
    rows = []
    for t in sorted(tasks, key=lambda t: t.due_at):
        s = states[t.id]
        if leadership:  # CEO / Owner: a reason is shown only once the Head / Manager approved it
            expl = "approved" if s["released"] else "not yet approved by the line"
        else:
            expl = "approved" if s["released"] else "awaiting approval" if s["explanations"] and s["awaiting_review"] else "needs update" if s["required"] and s["explanations"] else "missing" if s["required"] else "reviewed"
        rows.append({"task_no": t.task_no, "title": t.title, "employee": emps.get(t.assignee_id), "department": depts.get(t.department_id),
                     "priority": t.priority, "due": z(t.due_at), "days_overdue": (now - t.due_at).days, "escalation_level": s["escalation_level"],
                     "extensions": t.extension_count, "explanation": expl})  # fmt: skip
    return (["task_no", "title", "employee", "department", "priority", "due", "days_overdue", "escalation_level", "extensions", "explanation"], rows,
            {"overdue_tasks": len(rows)})  # fmt: skip


def extensions(db, p, f):
    tasks = _tasks(db, p, f, Task.extension_count > 0)
    emps, depts = _names(db)
    hist = defaultdict(list)
    if tasks:
        stmt = select(TaskDeadlineHistory).where(TaskDeadlineHistory.task_id.in_([t.id for t in tasks]), TaskDeadlineHistory.change_type != "initial")
        for h in db.scalars(stmt.order_by(TaskDeadlineHistory.id)):
            hist[h.task_id].append(h)
    rows = [{"task_no": t.task_no, "title": t.title, "employee": emps.get(t.assignee_id), "department": depts.get(t.department_id), "extensions": t.extension_count,
             "original_due": z(t.original_due_at), "current_due": z(t.due_at), "last_reason": (hist[t.id][-1].reason if hist[t.id] else None)} for t in sorted(tasks, key=lambda t: -t.extension_count)]  # fmt: skip
    return (["task_no", "title", "employee", "department", "extensions", "original_due", "current_due", "last_reason"], rows,
            {"tasks_with_extensions": len(rows), "total_extensions": sum(r["extensions"] for r in rows)})  # fmt: skip


def time_report(db, p, f):
    now = clock.utcnow()
    tasks = _tasks(db, p, f, *_range_extra(f, Task.assigned_at))
    emps, _depts = _names(db)
    worked = tq.active_seconds_map(db, [t.id for t in tasks], now)
    g: dict[int, dict] = defaultdict(lambda: {"tasks": 0, "estimated": 0.0, "active": 0.0, "elapsed": 0.0})
    for t in tasks:
        r = g[t.assignee_id]
        r["tasks"] += 1
        r["estimated"] += t.estimated_seconds
        r["active"] += worked.get(t.id, 0)
        end = t.completed_at or t.cancelled_at or now
        r["elapsed"] += max(0, (end - t.assigned_at).total_seconds())  # wall-clock since assignment: NOT working time
    rows = [{"employee": emps.get(e), "tasks": v["tasks"], "estimated_hours": _hours(v["estimated"]), "active_hours": _hours(v["active"]),
             "elapsed_hours": _hours(v["elapsed"])} for e, v in g.items()]  # fmt: skip
    rows.sort(key=lambda r: -r["active_hours"])
    return (["employee", "tasks", "estimated_hours", "active_hours", "elapsed_hours"], rows,
            {"estimated_hours": round(sum(r["estimated_hours"] for r in rows), 2), "active_hours": round(sum(r["active_hours"] for r in rows), 2)})  # fmt: skip


def rework(db, p, f):
    tasks = _tasks(db, p, f, Task.revert_count > 0)
    emps, depts = _names(db)
    rows = [{"task_no": t.task_no, "title": t.title, "employee": emps.get(t.assignee_id), "department": depts.get(t.department_id), "reverts": t.revert_count,
             "status": t.status} for t in sorted(tasks, key=lambda t: -t.revert_count)]  # fmt: skip
    return ["task_no", "title", "employee", "department", "reverts", "status"], rows, {"tasks_reworked": len(rows), "total_reverts": sum(r["reverts"] for r in rows)}


def blockers(db, p, f):
    tasks = {t.id: t for t in _tasks(db, p, f)}
    emps, _depts = _names(db)
    now = clock.utcnow()
    rows = []
    if tasks:
        for b in db.scalars(select(TaskBlocker).where(TaskBlocker.task_id.in_(list(tasks))).order_by(TaskBlocker.id.desc())):
            t = tasks[b.task_id]
            end = b.resolved_at or now
            rows.append({"task_no": t.task_no, "title": t.title, "employee": emps.get(t.assignee_id), "type": b.blocker_type, "blocker": b.title, "status": b.status,
                         "blocks_work": b.blocks_work, "opened_at": z(b.opened_at), "resolved_at": z(b.resolved_at), "waited_hours": _hours((end - b.opened_at).total_seconds())})  # fmt: skip
    return (["task_no", "title", "employee", "type", "blocker", "status", "blocks_work", "opened_at", "resolved_at", "waited_hours"], rows,
            {"blockers": len(rows), "open": sum(1 for r in rows if r["status"] in OPEN_BLOCKER)})  # fmt: skip


def workload(db, p, f):
    from app.modules.tasks import service

    people = service.workload(db, p) if p.has("task.assign") else [w for w in [service.my_workload(db, p)] if w]
    rows = [{"employee": w["full_name"], "department": w["department"], "open_tasks": w["open_tasks"], "overdue": w["overdue_tasks"], "due_next_7_days": w["due_next_7_days"],
             "remaining_hours": w["open_remaining_hours"], "capacity_hours_7d": w["capacity_hours_next_7_days"], "load_pct": w["load_pct"], "level": w["level"]} for w in people]  # fmt: skip
    return (["employee", "department", "open_tasks", "overdue", "due_next_7_days", "remaining_hours", "capacity_hours_7d", "load_pct", "level"], rows,
            {"people": len(rows), "overloaded": sum(1 for r in rows if r["level"] == "overloaded")})  # fmt: skip
