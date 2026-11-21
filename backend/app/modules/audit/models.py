from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import PK, Base, UTCDateTime


class ActivityLog(Base):
    """Append-only audit trail. The app DB role must have INSERT/SELECT only on this table."""

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_al_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_al_actor", "actor_user_id", "created_at"),
        Index("ix_al_action", "action", "created_at"),
        Index("ix_al_task", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(PK, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(50))
    task_id: Mapped[int | None] = mapped_column(PK, nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow, onupdate=clock.utcnow)
