"""Project endpoints (ADR 003). Thin: validation here, rules in projects.py."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.core.deps import get_principal, require
from app.core.schemas import Strict
from app.modules.rbac.policy import Principal
from app.modules.tasks import projects, service

router = APIRouter(tags=["projects"])


class PointIn(Strict):
    title: str = Field(min_length=2, max_length=200)
    details: str | None = Field(None, max_length=20000)
    expected_result: str | None = Field(None, max_length=5000)


class PointPatch(Strict):
    title: str | None = Field(None, min_length=2, max_length=200)
    details: str | None = Field(None, max_length=20000)
    expected_result: str | None = Field(None, max_length=5000)


class ProjectIn(Strict):
    name: str = Field(min_length=2, max_length=150)
    code: str | None = Field(None, min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(None, max_length=5000)
    expected_result: str | None = Field(None, max_length=5000)
    company_id: int | None = None
    assignee_id: int | None = None
    head_employee_id: int | None = None
    sub_head_employee_id: int | None = None
    qa_employee_id: int | None = None
    qa_employee_ids: list[int] | None = None
    member_ids: list[int] = Field(default_factory=list, max_length=500)
    points: list[PointIn] = Field(default_factory=list, max_length=200)
    department_id: int | None = None
    starts_on: date | None = None
    ends_on: date  # the project deadline: mandatory


class ProjectPatch(Strict):
    name: str | None = Field(None, min_length=2, max_length=150)
    description: str | None = Field(None, max_length=5000)
    expected_result: str | None = Field(None, max_length=5000)
    status: Literal["active", "on_hold", "archived"] | None = None
    company_id: int | None = None
    assignee_id: int | None = None
    head_employee_id: int | None = None
    sub_head_employee_id: int | None = None
    qa_employee_id: int | None = None
    qa_employee_ids: list[int] | None = None
    progress_pct: int | None = Field(None, ge=0, le=100)
    member_ids: list[int] | None = Field(None, max_length=500)
    starts_on: date | None = None
    ends_on: date | None = None


class AssignPointIn(Strict):
    assignee_id: int
    priority: Literal["critical", "high", "medium", "low"]
    due_date: date
    start_date: date | None = None
    estimated_hours: float | None = Field(None, gt=0, le=1000)
    instructions: str | None = Field(None, max_length=20000)
    category_id: int | None = None
    type_id: int | None = None
    head_employee_id: int | None = None
    sub_head_employee_id: int | None = None
    qa_employee_id: int | None = None
    qa_employee_ids: list[int] | None = None


class CompleteIn(Strict):
    note: str | None = Field(None, max_length=2000)


@router.get("/projects")
def list_projects(company_id: int | None = None, p: Principal = Depends(get_principal)):
    return projects.list_projects(p.db, p, company_id=company_id)


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, request: Request, p: Principal = Depends(require("project.manage"))):
    pr = projects.create_project(p.db, p, body.model_dump(), request)
    return projects.detail(p.db, p, pr)


@router.get("/projects/{project_id}")
def get_project(project_id: int, p: Principal = Depends(get_principal)):
    return projects.detail(p.db, p, projects.visible_project(p.db, p, project_id))


@router.patch("/projects/{project_id}")
def patch_project(project_id: int, body: ProjectPatch, request: Request, p: Principal = Depends(get_principal)):
    can_m = p.has("project.manage")
    data = body.model_dump(exclude_unset=True)
    if not can_m:
        other_fields = set(data.keys()) - {"progress_pct"}
        if other_fields or not p.employee:
            from app.core.errors import Forbidden
            raise Forbidden("You cannot edit this project")
    pr = projects.get_project(p.db, project_id)
    is_assignee = bool(p.employee and p.employee.id == pr.assignee_id)
    if not (can_m or is_assignee):
        from app.core.errors import Forbidden
        raise Forbidden("You cannot edit this project")
    if not can_m and is_assignee:
        # Assignee can only update progress_pct
        data = {k: v for k, v in data.items() if k == "progress_pct"}
    projects.update_project(p.db, p, pr, data, request)
    return projects.detail(p.db, p, pr)


@router.patch("/projects/{project_id}/points/{point_id}/toggle")
def toggle_point(project_id: int, point_id: int, request: Request, p: Principal = Depends(get_principal)):
    pr = projects.visible_project(p.db, p, project_id)
    return projects.point_dict(p.db, projects.toggle_point(p.db, p, pr, point_id, request))


@router.post("/projects/{project_id}/points", status_code=201)
def add_point(project_id: int, body: PointIn, request: Request, p: Principal = Depends(require("project.manage"))):
    pr = projects.get_project(p.db, project_id)
    return projects.point_dict(p.db, projects.add_point(p.db, p, pr, body.model_dump(), request))


@router.patch("/projects/{project_id}/points/{point_id}")
def patch_point(project_id: int, point_id: int, body: PointPatch, request: Request, p: Principal = Depends(require("project.manage"))):
    pr = projects.get_project(p.db, project_id)
    return projects.point_dict(p.db, projects.update_point(p.db, p, pr, point_id, body.model_dump(exclude_unset=True), request))


@router.delete("/projects/{project_id}/points/{point_id}", status_code=204)
def delete_point(project_id: int, point_id: int, request: Request, p: Principal = Depends(require("project.manage"))):
    projects.delete_point(p.db, p, projects.get_project(p.db, project_id), point_id, request)


@router.post("/projects/{project_id}/points/{point_id}/assign", status_code=201)
def assign_point(project_id: int, point_id: int, body: AssignPointIn, request: Request,
                 p: Principal = Depends(require("project.manage", "task.create", "task.assign"))):  # fmt: skip
    pr = projects.get_project(p.db, project_id)
    task, point, warnings = projects.assign_point(p.db, p, pr, point_id, body.model_dump(), request)
    return {"task": service.task_dict(p.db, task, detail=True), "point": projects.point_dict(p.db, point), "warnings": warnings}


@router.post("/projects/{project_id}/complete")
def complete_project(project_id: int, body: CompleteIn, request: Request, p: Principal = Depends(get_principal)):
    pr = projects.complete_project(p.db, p, project_id, body.note, request)
    return projects.detail(p.db, p, pr)

