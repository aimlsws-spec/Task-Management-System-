from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from app.core.deps import get_principal
from app.core.errors import AppError, Forbidden
from app.core.schemas import Strict
from app.modules.ai import provider, service
from app.modules.org.models import Department
from app.modules.rbac.policy import Principal
from app.modules.tasks.models import Project

router = APIRouter(prefix="/ai", tags=["ai"])


class AiRecommendIn(Strict):
    title: str = Field(min_length=2, max_length=200)
    company_id: int
    project_id: int | None = None
    department_id: int | None = None
    priority: str | None = None
    target_type: str = "task"  # "task" | "project"


class LearnEntityIn(Strict):
    company_id: int
    entity_name: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=2, max_length=2000)
    entity_type: str = "product"
    tech_stack: str | None = None
    default_notes: str | None = None


def _format_entity(ent):
    return {
        "id": ent.id,
        "company_id": ent.company_id,
        "entity_key": ent.entity_key,
        "entity_name": ent.entity_name,
        "entity_type": ent.entity_type,
        "description": ent.description,
        "tech_stack": ent.tech_stack,
        "default_notes": ent.default_notes,
        "created_at": ent.created_at.isoformat() if ent.created_at else None,
        "updated_at": ent.updated_at.isoformat() if ent.updated_at else None,
    }


@router.post("/recommend")
def recommend_details(
    body: AiRecommendIn,
    p: Principal = Depends(get_principal),
):
    """Recommends Description and Special Note for a task or project based on title and company memory."""
    if not p.can_access_company(body.company_id):
        raise Forbidden("You do not have access to this company")

    # Fetch known company entities
    known = service.list_entities(p.db, body.company_id)

    # Optional department context
    dept_name = None
    if body.department_id:
        dept = p.db.get(Department, body.department_id)
        if dept:
            dept_name = dept.name

    # Optional project context
    project_context = None
    if body.project_id:
        pr = p.db.get(Project, body.project_id)
        if pr:
            project_context = f"Project: {pr.name}"
            if pr.expected_result:
                project_context += f" | Expected: {pr.expected_result}"

    result = provider.generate_recommendation(
        title=body.title,
        target_type=body.target_type,
        priority=body.priority,
        department=dept_name,
        known_entities=known,
    )
    return result


@router.post("/learn-entity")
def learn_entity(
    body: LearnEntityIn,
    p: Principal = Depends(get_principal),
):
    """Save or update a company-specific product or domain term into the AI memory."""
    if not p.can_access_company(body.company_id):
        raise Forbidden("You do not have access to this company")

    ent = service.learn_entity(
        db=p.db,
        company_id=body.company_id,
        entity_name=body.entity_name,
        description=body.description,
        entity_type=body.entity_type,
        tech_stack=body.tech_stack,
        default_notes=body.default_notes,
        user_id=p.user.id,
    )
    return _format_entity(ent)


@router.get("/entities")
def list_entities(
    company_id: int = Query(...),
    p: Principal = Depends(get_principal),
):
    """List all saved domain knowledge entities for a company."""
    if not p.can_access_company(company_id):
        raise Forbidden("You do not have access to this company")
    return [_format_entity(e) for e in service.list_entities(p.db, company_id)]


@router.delete("/entities/{entity_id}", status_code=204)
def delete_entity(
    entity_id: int,
    company_id: int = Query(...),
    p: Principal = Depends(get_principal),
):
    """Delete a company knowledge entity."""
    if not p.can_access_company(company_id):
        raise Forbidden("You do not have access to this company")
    # Only Owner, CEO, or Admin can delete knowledge
    if not any(r in p.roles for r in ("owner", "ceo", "admin")):
        raise Forbidden("Only Owner, CEO, or Admin can delete company knowledge")
    service.delete_entity(p.db, entity_id, company_id)
