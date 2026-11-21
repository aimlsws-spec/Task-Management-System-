from fastapi import Request
from sqlalchemy.orm import Session

from app.modules.audit.models import ActivityLog


def log(
    db: Session,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | str,
    before: dict | None = None,
    after: dict | None = None,
    request: Request | None = None,
    task_id: int | None = None,
) -> None:
    ip = ua = rid = None
    if request is not None:
        ip = request.client.host if request.client else None
        ua = (request.headers.get("user-agent") or "")[:255] or None
        rid = getattr(request.state, "request_id", None)
    from app.modules.notifications.outbox import (
        from_audit,  # imported here: notifications builds on tasks and audit
    )

    from_audit(db, action, actor_user_id, task_id, before, after)  # same transaction: never lost, never for a rollback
    db.add(
        ActivityLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            task_id=task_id,
            before_json=before,
            after_json=after,
            ip=ip,
            user_agent=ua,
            request_id=rid,
        )
    )
