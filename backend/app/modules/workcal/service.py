"""Company work calendar: weekly pattern, nth-weekday rules (2nd/4th Saturday), holidays, leaves."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.settings_service import get_setting
from app.modules.org.models import Employee
from app.modules.workcal.models import EmployeeLeave, Holiday, WorkCalendarRule

DEFAULT_START, DEFAULT_END = time(9, 30), time(18, 30)
DEFAULT_BREAK = (time(13, 30), time(14, 0))


@dataclass(frozen=True)
class DayInfo:
    date: date
    is_working: bool
    reason: str  # 'rule', 'holiday', 'weekly_off', 'nth_weekday_off'
    windows: tuple[tuple[time, time], ...] = ()
    holiday_name: str | None = None

    @property
    def working_hours(self) -> float:
        total = 0.0
        for s, e in self.windows:
            total += (datetime.combine(self.date, e) - datetime.combine(self.date, s)).total_seconds() / 3600
        return total


def nth_in_month(d: date) -> int:
    """1 for days 1-7 (first occurrence of that weekday), 2 for 8-14, ..."""
    return (d.day - 1) // 7 + 1


def _windows(rule: WorkCalendarRule) -> tuple[tuple[time, time], ...]:
    if rule.break_starts_at and rule.break_ends_at:
        return ((rule.starts_at, rule.break_starts_at), (rule.break_ends_at, rule.ends_at))
    return ((rule.starts_at, rule.ends_at),)


def day_info(db: Session, d: date) -> DayInfo:
    hol = db.scalar(select(Holiday).where(Holiday.date == d))
    rules = db.scalars(
        select(WorkCalendarRule).where(
            WorkCalendarRule.weekday == d.weekday(),
            WorkCalendarRule.effective_from <= d,
            (WorkCalendarRule.effective_to.is_(None)) | (WorkCalendarRule.effective_to >= d),
        )
    ).all()
    nth = nth_in_month(d)
    specific = [r for r in rules if r.nth_in_month == nth]
    general = [r for r in rules if r.nth_in_month is None]
    rule = specific[0] if specific else (general[0] if general else None)

    if hol is not None:
        if hol.is_working_override and rule is not None:
            return DayInfo(d, True, "holiday_working", _windows(rule), hol.name)
        if hol.is_working_override:
            return DayInfo(d, True, "holiday_working", ((DEFAULT_START, DEFAULT_BREAK[0]), (DEFAULT_BREAK[1], DEFAULT_END)), hol.name)
        return DayInfo(d, False, "holiday", (), hol.name)
    if rule is None:
        return DayInfo(d, False, "weekly_off")
    if not rule.is_working:
        return DayInfo(d, False, "nth_weekday_off" if rule.nth_in_month else "weekly_off")
    return DayInfo(d, True, "rule", _windows(rule))


def is_working_day(db: Session, d: date) -> bool:
    return day_info(db, d).is_working


def add_working_days(db: Session, start: date, n: int) -> date:
    """Move n working days forward (n>0) or backward (n<0) from start (start itself not counted)."""
    step = 1 if n >= 0 else -1
    remaining, cur = abs(n), start
    for _ in range(3700):  # safety bound (~10 years)
        if remaining == 0:
            return cur
        cur += timedelta(days=step)
        if is_working_day(db, cur):
            remaining -= 1
    raise ValueError("No working days found in range; check calendar rules")


def company_tz(db: Session) -> ZoneInfo:
    return ZoneInfo(get_setting(db, "company_timezone"))


def local_to_utc(db: Session, local_naive: datetime) -> datetime:
    return local_naive.replace(tzinfo=company_tz(db)).astimezone(UTC).replace(tzinfo=None)


def utc_to_local(db: Session, utc_naive: datetime) -> datetime:
    return utc_naive.replace(tzinfo=UTC).astimezone(company_tz(db)).replace(tzinfo=None)


def parse_clock(value: str) -> time:
    h, m = value.split(":")[:2]
    return time(int(h), int(m))


def resolve_eod_utc(db: Session, d: date) -> datetime:
    """'Deadline: 20 Nov, EOD' -> that day's end-of-day clock time in company tz, as naive UTC."""
    return local_to_utc(db, datetime.combine(d, parse_clock(get_setting(db, "eod_time"))))


def deadline_warning(db: Session, due_utc: datetime) -> str | None:
    """Non-blocking warning when a deadline lands on a non-working day."""
    local = utc_to_local(db, due_utc)
    info = day_info(db, local.date())
    if info.is_working:
        return None
    label = {
        "holiday": f"a holiday ({info.holiday_name})",
        "nth_weekday_off": "an off Saturday",
        "weekly_off": "a weekly off day",
    }.get(info.reason, "a non-working day")
    return f"The deadline falls on {label}."


def capacity_hours(db: Session, employee: Employee, start: date, end: date) -> Decimal:
    """Productive hours available in [start, end] inclusive: working days minus approved leave."""
    leaves = db.scalars(
        select(EmployeeLeave).where(
            EmployeeLeave.employee_id == employee.id,
            EmployeeLeave.status == "approved",
            EmployeeLeave.to_date >= start,
            EmployeeLeave.from_date <= end,
        )
    ).all()
    total, cur = Decimal("0"), start
    while cur <= end:
        if is_working_day(db, cur) and not any(lv.from_date <= cur <= lv.to_date for lv in leaves):
            total += employee.daily_capacity_hours
        cur += timedelta(days=1)
    return total


def seed_default_calendar(db: Session) -> None:
    """Mon-Sat working, Sunday off, 2nd & 4th Saturday off. Idempotent."""
    if db.scalar(select(WorkCalendarRule.id).limit(1)) is not None:
        return
    for wd in range(0, 6):  # Mon..Sat working
        db.add(WorkCalendarRule(weekday=wd, nth_in_month=None, is_working=True))
    db.add(WorkCalendarRule(weekday=6, nth_in_month=None, is_working=False))  # every Sunday off
    for nth in (2, 4):
        db.add(WorkCalendarRule(weekday=5, nth_in_month=nth, is_working=False))
    db.flush()
