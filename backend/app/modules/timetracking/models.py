from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import PK, Base, UTCDateTime


class TimeLog(Base):
    """One work session. The server clock is the only time source; the browser never supplies timestamps."""

    __tablename__ = "task_time_logs"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_tl_range"),
        # A generated column holds the employee id while a session is open, NULL once closed. UNIQUE on it
        # means the DATABASE itself refuses a second open timer for the same employee (MySQL has no partial indexes).
        UniqueConstraint("active_employee_key", name="uq_tl_one_active"),
        Index("ix_tl_task", "task_id"),
        Index("ix_tl_emp", "employee_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set when the session closes
    source: Mapped[str] = mapped_column(String(15), default="timer")  # timer / manual / auto_closed
    end_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # stopped / paused / switched / on_hold / completed / cancelled / reassigned / auto_timeout
    status: Mapped[str] = mapped_column(String(10), default="approved")  # approved / pending / rejected
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)  # False = provisional (auto-closed, not yet confirmed)
    continuous_since: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # reset by "Still working? Continue"
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    active_employee_key: Mapped[int | None] = mapped_column(
        BigInteger, Computed("CASE WHEN ended_at IS NULL AND status = 'approved' THEN employee_id END", persisted=True), nullable=True
    )


class TimeCorrection(Base):
    """Every change to recorded time is a row here; the original session is never overwritten silently."""

    __tablename__ = "task_time_corrections"
    __table_args__ = (Index("ix_tc_status", "status", "created_at"), Index("ix_tc_emp", "employee_id"))

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    time_log_id: Mapped[int | None] = mapped_column(ForeignKey("task_time_logs.id"), nullable=True)  # NULL = missing time to add
    kind: Mapped[str] = mapped_column(String(10))  # add / edit / trim
    old_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    old_ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    new_started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    new_ended_at: Mapped[datetime] = mapped_column(UTCDateTime)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending / approved / rejected
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TimerCheckin(Base):
    """'Still working on this?' prompts. UNIQUE per session+kind so a repeated job run never duplicates one."""

    __tablename__ = "timer_checkins"
    __table_args__ = (UniqueConstraint("time_log_id", "kind", name="uq_checkin"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    time_log_id: Mapped[int] = mapped_column(ForeignKey("task_time_logs.id"))
    kind: Mapped[str] = mapped_column(String(20))  # after_4h / after_8h / evening
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    response: Mapped[str | None] = mapped_column(String(10), nullable=True)  # continue / stop
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
