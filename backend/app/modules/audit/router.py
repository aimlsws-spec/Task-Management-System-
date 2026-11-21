from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core.deps import require
from app.modules.audit.models import ActivityLog
from app.modules.rbac.policy import Principal

router = APIRouter(prefix="/admin", tags=["audit"])


@router.get("/audit-logs")
def audit_logs(
    action: str | None = None, entity_type: str | None = None, actor_user_id: int | None = None,
    page: int = 1, page_size: int = 50, p: Principal = Depends(require("audit.view")),
):  # fmt: skip
    page_size = max(1, min(page_size, 200))
    stmt = select(ActivityLog)
    if action:
        stmt = stmt.where(ActivityLog.action == action)
    if entity_type:
        stmt = stmt.where(ActivityLog.entity_type == entity_type)
    if actor_user_id:
        stmt = stmt.where(ActivityLog.actor_user_id == actor_user_id)
    total = p.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = p.db.scalars(stmt.order_by(ActivityLog.id.desc()).offset((page - 1) * page_size).limit(page_size))
    items = [
        {"id": r.id, "actor_user_id": r.actor_user_id, "action": r.action, "entity_type": r.entity_type,
         "entity_id": r.entity_id, "before": r.before_json, "after": r.after_json, "ip": r.ip,
         "created_at": r.created_at.isoformat() + "Z"}
        for r in rows
    ]  # fmt: skip
    return {"items": items, "total": total, "page": page, "page_size": page_size}
