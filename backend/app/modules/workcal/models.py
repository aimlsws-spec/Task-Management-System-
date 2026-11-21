from datetime import date, time

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base


class WorkCalendarRule(Base):
    """weekday 0=Mon..6=Sun. nth_in_month NULL = every occurrence; 1..5 = that occurrence only.
    The most specific matching rule (nth set) wins over the general one."""

    __tablename__ = "work_calendar_rules"
    __table_args__ = (Index("ix_wcr_weekday", "weekday"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)
    nth_in_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_working: Mapped[bool] = mapped_column(Boolean)
    starts_at: Mapped[time] = mapped_column(Time, default=time(9, 30))
    ends_at: Mapped[time] = mapped_column(Time, default=time(18, 30))
    break_starts_at: Mapped[time | None] = mapped_column(Time, nullable=True, default=time(13, 30))
    break_ends_at: Mapped[time | None] = mapped_column(Time, nullable=True, default=time(14, 0))
    effective_from: Mapped[date] = mapped_column(Date, default=date(2000, 1, 1))
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(150))
    is_working_override: Mapped[bool] = mapped_column(Boolean, default=False)


class EmployeeLeave(Base):
    __tablename__ = "employee_leaves"
    __table_args__ = (Index("ix_leave_emp", "employee_id", "from_date", "to_date"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(30), default="leave")
    status: Mapped[str] = mapped_column(String(20), default="approved")
