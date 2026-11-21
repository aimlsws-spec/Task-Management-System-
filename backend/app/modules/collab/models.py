from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import PK, Base, UTCDateTime

BLOCKER_TYPES = ("technical", "dependency", "information", "resource", "access", "other")
BLOCKER_STATUSES = ("open", "acknowledged", "in_progress", "resolved", "closed")
OPEN_BLOCKER = ("open", "acknowledged", "in_progress")  # still an unresolved problem


class TaskBlocker(Base):
    """Something stopping (or hampering) the work, e.g. missing credentials. Each change is an event row."""

    __tablename__ = "task_blockers"
    __table_args__ = (Index("ix_blk_task", "task_id", "status"), Index("ix_blk_status", "status", "opened_at"))

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    raised_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    blocker_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocks_work: Mapped[bool] = mapped_column(Boolean, default=True)  # True: the task becomes Blocked and the timer stops
    expected_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="open")
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # who is dealing with it
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("task_attachments.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalated_to_leadership: Mapped[bool] = mapped_column(Boolean, default=False)


class TaskBlockerEvent(Base):
    """Append-only history of one blocker: raised, acknowledged, replies, assignments, escalation, resolution..."""

    __tablename__ = "task_blocker_events"
    __table_args__ = (Index("ix_blke_blocker", "blocker_id", "created_at"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(ForeignKey("task_blockers.id"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # NULL = system
    event: Mapped[str] = mapped_column(String(20))
    from_status: Mapped[str | None] = mapped_column(String(15), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(15), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskComment(Base):
    """The task's discussion: comments, questions, clarifications and replies. Never deleted by anyone."""

    __tablename__ = "task_comments"
    __table_args__ = (Index("ix_cmt_task", "task_id", "created_at"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("task_comments.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(15))  # comment / question / clarification / reply
    body: Mapped[str] = mapped_column(Text)
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("task_attachments.id"), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class CommentMention(Base):
    __tablename__ = "comment_mentions"

    comment_id: Mapped[int] = mapped_column(ForeignKey("task_comments.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
