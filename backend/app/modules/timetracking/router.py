from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.core import clock
from app.core.config import get_settings
from app.core.deps import require
from app.core.errors import NotFound
from app.core.schemas import Strict
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal
from app.modules.tasks import service as tasks_service
from app.modules.tasks.models import Task
from app.modules.timetracking import guard
from app.modules.timetracking import service as ts
from app.modules.timetracking.models import TimeCorrection, TimeLog
from app.modules.workcal import service as cal

router = APIRouter(tags=["time"])


class ConfirmIn(Strict):
    ended_at: datetime | None = None  # only earlier than the auto-closed end (shorten)


class AdjustIn(Strict):
    started_at: datetime
    ended_at: datetime
    reason: str = Field(min_length=5, max_length=2000)


class MissingTimeIn(Strict):
    task_id: int
    started_at: datetime
    ended_at: datetime
    reason: str = Field(min_length=5, max_length=2000)


class DecisionIn(Strict):
    decision: Literal["approve", "reject"]
    note: str | None = Field(None, max_length=2000)


# ---------------------------------------------------------------- my timer


@router.get("/time/active")
def active(p: Principal = Depends(require("task.view"))):
    """The running timer (if any) with its check-in prompt. The page re-reads this after refresh, so state is server-side."""
    if not get_settings().time_tracking:
        return {"active": None, "server_time": clock.utcnow().isoformat() + "Z"}
    return ts.active_view(p.db, p)


@router.post("/time/heartbeat")
def heartbeat(p: Principal = Depends(require("task.view"))):
    return ts.heartbeat(p.db, p)


@router.post("/time/checkin/continue")
def checkin_continue(p: Principal = Depends(require("task.view"))):
    return ts.continue_session(p.db, p)


@router.get("/time/unconfirmed")
def unconfirmed(p: Principal = Depends(require("task.view"))):
    """Auto-closed sessions waiting for the employee to confirm (they may shorten them)."""
    return ts.unconfirmed_for(p.db, p)


@router.get("/me/workload")
def my_workload(p: Principal = Depends(require("task.view"))):
    return tasks_service.my_workload(p.db, p)


# ---------------------------------------------------------------- logs (own + team)


@router.get("/time/logs")
def logs(
    employee_id: int | None = None, task_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
    page: int = 1, page_size: int = 50, p: Principal = Depends(require("time.view")),
):  # fmt: skip
    """Sessions of people in your `time.view` scope (employees see their own)."""
    now = clock.utcnow()
    E = aliased(Employee)
    stmt = select(TimeLog, Task, E).join(Task, Task.id == TimeLog.task_id).join(E, E.id == TimeLog.employee_id).where(TimeLog.status == "approved")
    ids = p.scope_employee_ids("time.view")
    if ids is not None:
        stmt = stmt.where(TimeLog.employee_id.in_(ids))
    if employee_id:
        stmt = stmt.where(TimeLog.employee_id == employee_id)
    if task_id:
        stmt = stmt.where(TimeLog.task_id == task_id)
    if date_from:
        stmt = stmt.where(TimeLog.started_at >= cal.local_to_utc(p.db, datetime.combine(date_from, time.min)))
    if date_to:
        stmt = stmt.where(TimeLog.started_at < cal.local_to_utc(p.db, datetime.combine(date_to + timedelta(days=1), time.min)))
    total = p.db.scalar(select(func.count()).select_from(stmt.subquery()))
    page_size = max(1, min(page_size, 200))
    rows = p.db.execute(stmt.order_by(TimeLog.started_at.desc()).offset((max(1, page) - 1) * page_size).limit(page_size)).all()
    items = [{**ts.session_dict(p.db, lg, now), "task": {"id": t.id, "task_no": t.task_no, "title": t.title},
              "employee": {"id": e.id, "full_name": e.full_name}} for lg, t, e in rows]  # fmt: skip
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_seconds": sum(i["seconds"] for i in items)}


@router.post("/time/logs/{log_id}/confirm")
def confirm(log_id: int, request: Request, body: ConfirmIn | None = None, p: Principal = Depends(require("task.view"))):
    lg = p.db.get(TimeLog, log_id) or _missing()
    return ts.session_dict(p.db, ts.confirm_log(p.db, p, lg, body.ended_at if body else None, request), clock.utcnow())


@router.post("/time/logs/{log_id}/adjust")
def adjust(log_id: int, body: AdjustIn, request: Request, p: Principal = Depends(require("time.correct.approve"))):
    lg = p.db.get(TimeLog, log_id) or _missing()
    return ts.session_dict(p.db, ts.adjust_log(p.db, p, lg, body.started_at, body.ended_at, body.reason, request), clock.utcnow())


# ---------------------------------------------------------------- missing time and corrections


@router.post("/time/corrections", status_code=201)
def request_time(body: MissingTimeIn, request: Request, p: Principal = Depends(require("task.view"))):
    """The employee forgot the timer: ask for the time to be added (a manager approves; never applied silently)."""
    t = tasks_service.get_visible_task(p.db, p, body.task_id)
    return ts.correction_dict(ts.request_missing_time(p.db, p, t, body.started_at, body.ended_at, body.reason, request))


@router.get("/time/corrections")
def corrections(status: str | None = "pending", p: Principal = Depends(require("task.view"))):
    """Mine, plus (for managers) those of people in their `time.correct.approve` scope."""
    stmt = select(TimeCorrection, Employee.full_name, Task.task_no, Task.title).join(Employee, Employee.id == TimeCorrection.employee_id).join(Task, Task.id == TimeCorrection.task_id)
    me = p.employee.id if p.employee else -1
    ids = p.scope_employee_ids("time.correct.approve") if p.has("time.correct.approve") else set()
    stmt = stmt.where(TimeCorrection.employee_id == me) if not p.has("time.correct.approve") else (stmt if ids is None else stmt.where(TimeCorrection.employee_id.in_(ids | {me})))
    if status:
        stmt = stmt.where(TimeCorrection.status == status)
    rows = p.db.execute(stmt.order_by(TimeCorrection.id.desc()).limit(200)).all()
    return [{**ts.correction_dict(c), "employee": name, "task": {"task_no": no, "title": title},
             "can_decide": ts._can_decide(p, c.employee_id)} for c, name, no, title in rows]  # fmt: skip


@router.post("/time/corrections/{cid}/decision")
def decide(cid: int, body: DecisionIn, request: Request, p: Principal = Depends(require("time.correct.approve"))):
    c = p.db.get(TimeCorrection, cid) or _missing()
    return ts.correction_dict(ts.decide_correction(p.db, p, c, body.decision == "approve", body.note, request))


# ---------------------------------------------------------------- jobs (until Phase 6 schedules them)


@router.post("/admin/jobs/timer-guard")
def run_timer_guard(p: Principal = Depends(require("settings.manage"))):
    """Run the forgotten-timer guard now (auto-close past the cap, create 'still working?' check-ins)."""
    return guard.run_guard(p.db)


def _missing():
    raise NotFound("Time entry")
