from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Response

from app.core.deps import require
from app.core.errors import AppError, NotFound
from app.modules.audit import service as audit
from app.modules.rbac.policy import Principal
from app.modules.reports import export, service

router = APIRouter(tags=["reports"])
Priority = Literal["critical", "high", "medium", "low"]


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require("dashboard.view", "task.view"))):
    """Role-aware summary: company (Owner/CEO), team (Manager), department (Head), self (employee)."""
    return service.dashboard(p.db, p)


@router.get("/reports")
def catalogue(p: Principal = Depends(require("report.view"))):
    return [{"name": k, "title": v} for k, v in service.REPORTS.items()]


def _filters(department_id, assignee_id, priority, date_from, date_to) -> dict:
    return {"department_id": department_id, "assignee_id": assignee_id, "priority": priority, "date_from": date_from, "date_to": date_to}


@router.get("/reports/{name}")
def report(name: str, department_id: int | None = None, assignee_id: int | None = None, priority: Priority | None = None,
           date_from: date | None = None, date_to: date | None = None, p: Principal = Depends(require("report.view", "task.view"))):  # fmt: skip
    if name not in service.REPORTS:
        raise NotFound("Report")
    return service.run(p.db, p, name, _filters(department_id, assignee_id, priority, date_from, date_to))


@router.get("/reports/{name}/export")
def export_report(name: str, format: Literal["csv", "xlsx"] = "csv", department_id: int | None = None, assignee_id: int | None = None,
                  priority: Priority | None = None, date_from: date | None = None, date_to: date | None = None,
                  p: Principal = Depends(require("report.export", "task.view"))):  # fmt: skip
    if name not in service.REPORTS:
        raise NotFound("Report")
    data = service.run(p.db, p, name, _filters(department_id, assignee_id, priority, date_from, date_to))
    if len(data["rows"]) > 50000:
        raise AppError("EXPORT_TOO_LARGE", "Narrow the filters: exports are limited to 50,000 rows", 422)
    audit.log(p.db, p.user.id, "REPORT_EXPORTED", "report", name, after={"format": format, "rows": len(data["rows"])})
    if format == "xlsx":
        body, mime = export.to_xlsx(name, data["columns"], data["rows"]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        body, mime = export.to_csv(data["columns"], data["rows"]), "text/csv; charset=utf-8"
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="tms-{name}-{date.today()}.{format}"'})
