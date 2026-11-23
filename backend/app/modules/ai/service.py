import re
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.modules.ai.models import CompanyKnowledge


def normalize_key(name: str) -> str:
    """Turn display name into a clean search key: e.g. 'Elala App' -> 'elala', 'HRMS' -> 'hrms'."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s_-]", "", name.strip().lower())
    return re.sub(r"[\s_-]+", "_", cleaned).strip("_")


def list_entities(db: Session, company_id: int) -> list[CompanyKnowledge]:
    return list(db.scalars(
        select(CompanyKnowledge)
        .where(CompanyKnowledge.company_id == company_id)
        .order_by(CompanyKnowledge.entity_name.asc())
    ))


def get_entity_by_id(db: Session, entity_id: int) -> CompanyKnowledge | None:
    return db.get(CompanyKnowledge, entity_id)


def get_entity_by_key(db: Session, company_id: int, key: str) -> CompanyKnowledge | None:
    return db.scalar(
        select(CompanyKnowledge)
        .where(CompanyKnowledge.company_id == company_id, CompanyKnowledge.entity_key == key)
    )


def find_matching_entities(db: Session, company_id: int, text: str) -> list[CompanyKnowledge]:
    """Find known company entities referenced in the given title or text."""
    all_entities = list_entities(db, company_id)
    if not all_entities:
        return []
    text_lower = text.lower()
    matches = []
    for ent in all_entities:
        key_pattern = r"\b" + re.escape(ent.entity_key.replace("_", " ")) + r"\b"
        name_pattern = r"\b" + re.escape(ent.entity_name.lower()) + r"\b"
        if re.search(key_pattern, text_lower) or re.search(name_pattern, text_lower) or ent.entity_key in text_lower:
            matches.append(ent)
    return matches


def learn_entity(
    db: Session,
    company_id: int,
    entity_name: str,
    description: str,
    entity_type: str = "product",
    tech_stack: str | None = None,
    default_notes: str | None = None,
    user_id: int | None = None,
) -> CompanyKnowledge:
    name_clean = entity_name.strip()
    if not name_clean:
        raise AppError("INVALID_NAME", "Entity name cannot be empty", 422)
    key = normalize_key(name_clean)
    existing = get_entity_by_key(db, company_id, key)
    if existing:
        existing.entity_name = name_clean
        existing.description = description.strip()
        existing.entity_type = entity_type or existing.entity_type
        if tech_stack is not None:
            existing.tech_stack = tech_stack.strip() or None
        if default_notes is not None:
            existing.default_notes = default_notes.strip() or None
        db.commit()
        db.refresh(existing)
        return existing

    new_ent = CompanyKnowledge(
        company_id=company_id,
        entity_key=key,
        entity_name=name_clean,
        entity_type=entity_type or "product",
        description=description.strip(),
        tech_stack=tech_stack.strip() if tech_stack else None,
        default_notes=default_notes.strip() if default_notes else None,
        created_by_user_id=user_id,
    )
    db.add(new_ent)
    db.commit()
    db.refresh(new_ent)
    return new_ent


def delete_entity(db: Session, entity_id: int, company_id: int) -> None:
    ent = get_entity_by_id(db, entity_id)
    if not ent or ent.company_id != company_id:
        raise NotFound("Company knowledge entity not found")
    db.delete(ent)
    db.commit()
