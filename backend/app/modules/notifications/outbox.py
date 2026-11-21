"""Transactional outbox: an event is stored in the same database transaction as the thing that happened."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.notifications.models import OutboxEvent


def emit(db: Session, event_type: str, task_id: int | None = None, actor_user_id: int | None = None,
         payload: dict | None = None, dedupe_key: str | None = None) -> bool:  # fmt: skip
    """Record an event. With a dedupe_key (scheduler events) a repeat is silently ignored. Returns True if recorded."""
    try:
        with db.begin_nested():
            db.add(OutboxEvent(event_type=event_type, task_id=task_id, actor_user_id=actor_user_id, payload=payload or {}, dedupe_key=dedupe_key))
            db.flush()
    except IntegrityError:
        return False
    return True


def from_audit(db: Session, action: str, actor_user_id: int | None, task_id: int | None, before: dict | None, after: dict | None) -> None:
    """Every audited task action is also an event. Rules decide whether anyone cares (no rule = no notification)."""
    if task_id is None:
        return
    db.add(OutboxEvent(event_type=action, task_id=task_id, actor_user_id=actor_user_id, payload={"before": before or {}, "after": after or {}}))
