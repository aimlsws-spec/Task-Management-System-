from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import PK, Base, UTCDateTime


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    head_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", use_alter=True, name="fk_dept_head"), nullable=True
    )
    # ADR 008: the department's QA tester. Work finished by anyone in the department goes to this person first (unless the
    # task or its project names its own QA). Empty = no QA step for the department.
    qa_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", use_alter=True, name="fk_dept_qa"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # System departments (e.g. the holding area for people who have not finished sign-up) cannot be deleted.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    # Whether new employees may pick this department when they sign up (Admin controls this).
    self_service: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (Index("ix_emp_dept_status", "department_id", "status"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    employee_code: Mapped[str] = mapped_column(String(30), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    # active / on_leave / inactive / pending_setup (signed up, has not yet chosen department + designation)
    status: Mapped[str] = mapped_column(String(20), default="active")
    joined_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    left_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_capacity_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("8.50"))
    can_receive_tasks: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class ReportingRelationship(Base):
    """Effective-dated adjacency list. Exactly one active 'primary' manager per employee."""

    __tablename__ = "reporting_relationships"
    __table_args__ = (
        CheckConstraint("employee_id <> reports_to_id", name="ck_rr_not_self"),
        Index("ix_rr_emp", "employee_id", "effective_to"),
        Index("ix_rr_boss", "reports_to_id", "effective_to"),
        UniqueConstraint("employee_id", "relation_type", "active_flag", name="uq_rr_one_active"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    reports_to_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    relation_type: Mapped[str] = mapped_column(String(20), default="primary")
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # 1 while open, NULL once closed -> UNIQUE allows many closed rows but only one open row.
    active_flag: Mapped[int | None] = mapped_column(
        Computed("CASE WHEN effective_to IS NULL THEN 1 END", persisted=True), nullable=True
    )


class ManagerDepartment(Base):
    """Extra departments a manager supervises beyond their reporting subtree."""

    __tablename__ = "manager_departments"

    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), primary_key=True)


class RoleInvite(Base):
    """An email the Admin has registered for a role (Owner, CEO, ...). Whoever signs up with exactly this email
    receives the role. One row per email; claimed once; never edited, only revoked while unclaimed (ADR 002)."""

    __tablename__ = "role_invites"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    claimed_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
