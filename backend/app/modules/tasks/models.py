from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import PK, Base, UTCDateTime

PRIORITIES = ("critical", "high", "medium", "low")
PRIORITY_RANK = {"critical": 1, "high": 2, "medium": 3, "low": 4}
STATUSES = (
    "assigned", "acknowledged", "in_progress", "on_hold", "blocked",
    "under_review", "completed", "reopened", "cancelled",
)  # fmt: skip
TERMINAL = ("completed", "cancelled")
OPEN_STATUSES = tuple(s for s in STATUSES if s not in TERMINAL)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    owner_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/on_hold/completed/archived
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    # ADR 003: what the owner expects at the end, who heads it, and how it was signed off
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    head_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    qa_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)  # ADR 006: QA for development projects
    progress_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectMember(Base):
    """An employee on the project team. With a team, tasks in the project can only go to team members (or the head)."""

    __tablename__ = "project_members"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), primary_key=True)


class ProjectPoint(Base):
    """Planned work inside a project that is not a task yet. Assigning it creates the task and links it here."""

    __tablename__ = "project_points"
    __table_args__ = (Index("ix_point_project", "project_id", "position"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, unique=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskCategory(Base):
    __tablename__ = "task_categories"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaskType(Base):
    __tablename__ = "task_types"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Task(Base):
    """Current state of a task only. History lives in the *_history / assignments / activity tables."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("priority IN ('critical','high','medium','low')", name="ck_task_priority"),
        CheckConstraint(
            "status IN ('assigned','acknowledged','in_progress','on_hold','blocked',"
            "'under_review','completed','reopened','cancelled')",
            name="ck_task_status",
        ),
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="ck_task_progress"),
        CheckConstraint("estimated_seconds > 0", name="ck_task_estimate"),
        Index("ix_task_assignee", "assignee_id", "status", "due_at"),
        Index("ix_task_dept", "department_id", "status", "due_at"),
        Index("ix_task_status_due", "status", "due_at"),
        Index("ix_task_assigner", "assigned_by_id"),
        Index("ix_task_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_no: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("task_categories.id"), nullable=True)
    type_id: Mapped[int | None] = mapped_column(ForeignKey("task_types.id"), nullable=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    priority: Mapped[str] = mapped_column(String(10))
    priority_rank: Mapped[int] = mapped_column(SmallInteger)  # 1 critical .. 4 low, for sorting
    status: Mapped[str] = mapped_column(String(20), default="assigned")
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_due_at: Mapped[datetime] = mapped_column(UTCDateTime)  # immutable once created
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    deadline_version: Mapped[int] = mapped_column(Integer, default=1)
    extension_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_seconds: Mapped[int] = mapped_column(Integer)
    progress_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    first_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    verified_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revert_count: Mapped[int] = mapped_column(Integer, default=0)
    # ADR 003/006: while under review, whose turn it is: 'qa', 'head' or 'leadership' (CEO/Owner)
    review_stage: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # ADR 006: optional per-task head and QA (else the project's). No head/QA/project = one person's own work, no chain.
    head_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    qa_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    status_before_block: Mapped[str | None] = mapped_column(String(20), nullable=True)  # restored when the last blocker clears
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic lock
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow, onupdate=clock.utcnow)


class TaskAssignment(Base):
    """Who held the task and when (reassignments keep full history)."""

    __tablename__ = "task_assignments"
    __table_args__ = (Index("ix_ta_task", "task_id"), Index("ix_ta_assignee", "assignee_id", "unassigned_at"))

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    assignee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    unassigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"
    __table_args__ = (Index("ix_tsh_task", "task_id", "created_at"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # NULL = system
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskDeadlineHistory(Base):
    """Append-only. The first row is the original deadline; Phase 5 adds extensions."""

    __tablename__ = "task_deadline_history"
    __table_args__ = (UniqueConstraint("task_id", "deadline_version", name="uq_tdh_version"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    deadline_version: Mapped[int] = mapped_column(Integer)
    previous_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    new_due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    changed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    change_type: Mapped[str] = mapped_column(String(20))  # initial / extension / shorten
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskAttachment(Base):
    __tablename__ = "task_attachments"
    __table_args__ = (Index("ix_att_task", "task_id"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_key: Mapped[str] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskUpdate(Base):
    """Progress updates. Append-only."""

    __tablename__ = "task_updates"
    __table_args__ = (
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="ck_tu_progress"),
        Index("ix_tu_task", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    progress_pct: Mapped[int] = mapped_column(SmallInteger)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskCompletionAssurance(Base):
    """What the employee confirmed when marking work done / submitting it. One row per attempt. Append-only."""

    __tablename__ = "task_completion_assurances"
    __table_args__ = (UniqueConstraint("task_id", "attempt_no", name="uq_tca_attempt"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    attempt_no: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    tested: Mapped[bool] = mapped_column(Boolean)
    test_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    no_time_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskVerification(Base):
    __tablename__ = "task_verifications"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    verified_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskRevert(Base):
    """A completed (or submitted) piece of work sent back, e.g. QA found the feature not working."""

    __tablename__ = "task_reverts"
    __table_args__ = (Index("ix_trv_reason", "reason_code", "created_at"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)  # which completion was sent back
    reverted_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason_code: Mapped[str] = mapped_column(String(25))  # qa_defect / incomplete / requirement_change / other
    reason: Mapped[str] = mapped_column(Text)
    found_by: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. "QA"
    bug_sheet_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class DelayReason(Base):
    """An explanation for a missed deadline. Append-only: never edited or deleted, only followed by newer ones."""

    __tablename__ = "task_delay_reasons"
    __table_args__ = (
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="ck_dr_progress"),
        Index("ix_dr_task", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    deadline_version: Mapped[int] = mapped_column(Integer)  # which deadline was missed
    kind: Mapped[str] = mapped_column(String(10))  # initial / update
    reason: Mapped[str] = mapped_column(Text)
    progress_pct: Mapped[int] = mapped_column(SmallInteger)
    work_completed: Mapped[str] = mapped_column(Text)
    remaining_work: Mapped[str] = mapped_column(Text)
    blockers_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_completion_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("task_attachments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class DelayReview(Base):
    """A manager's decision on one explanation. Accepting an explanation never completes the task."""

    __tablename__ = "task_delay_reviews"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    delay_reason_id: Mapped[int] = mapped_column(ForeignKey("task_delay_reasons.id"), index=True)
    reviewer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    # accepted / clarification_requested / rejected / revised_deadline_approved / escalated
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_history_id: Mapped[int | None] = mapped_column(ForeignKey("task_deadline_history.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class ExtensionRequest(Base):
    """The employee asks for a later deadline; a manager decides. Employees never change deadlines themselves."""

    __tablename__ = "deadline_extension_requests"
    __table_args__ = (Index("ix_er_task", "task_id", "status"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deadline_version: Mapped[int] = mapped_column(Integer)  # the deadline in force when asked
    requested_due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending / approved / rejected
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # may differ from what was asked
    deadline_history_id: Mapped[int | None] = mapped_column(ForeignKey("task_deadline_history.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class TaskOwnership(Base):
    """A Department Head takes responsibility for a task held by someone in their department (append-only)."""

    __tablename__ = "task_head_ownership"
    __table_args__ = (UniqueConstraint("task_id", "employee_id", name="uq_task_head_owner"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


# ---- The original deadline can never change, whichever code path tries (service, script, future feature).
from sqlalchemy import event, inspect  # noqa: E402


@event.listens_for(Task, "before_update")
def _protect_original_deadline(mapper, connection, target) -> None:
    if inspect(target).attrs.original_due_at.history.has_changes():
        raise RuntimeError("tasks.original_due_at is immutable")
