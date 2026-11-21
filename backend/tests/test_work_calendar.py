from datetime import date, datetime
from decimal import Decimal

from app.modules.org.models import Employee
from app.modules.workcal import service
from app.modules.workcal.models import EmployeeLeave, Holiday
from app.modules.workcal.service import seed_default_calendar


def cal(db):
    seed_default_calendar(db)
    db.commit()


def test_nth_in_month():
    assert service.nth_in_month(date(2026, 11, 7)) == 1
    assert service.nth_in_month(date(2026, 11, 14)) == 2
    assert service.nth_in_month(date(2026, 11, 28)) == 4


def test_sundays_always_off(db):
    cal(db)
    for d in (date(2026, 11, 1), date(2026, 11, 8), date(2026, 11, 15), date(2026, 11, 22), date(2026, 11, 29)):
        assert not service.is_working_day(db, d)


def test_2nd_and_4th_saturday_off_others_working(db):
    cal(db)
    # November 2026 Saturdays: 7, 14, 21, 28
    assert service.is_working_day(db, date(2026, 11, 7))  # 1st
    assert not service.is_working_day(db, date(2026, 11, 14))  # 2nd
    assert service.is_working_day(db, date(2026, 11, 21))  # 3rd
    assert not service.is_working_day(db, date(2026, 11, 28))  # 4th
    assert service.day_info(db, date(2026, 11, 14)).reason == "nth_weekday_off"


def test_5th_saturday_is_working(db):
    cal(db)
    assert service.nth_in_month(date(2026, 10, 31)) == 5
    assert service.is_working_day(db, date(2026, 10, 31))


def test_working_windows_and_hours(db):
    cal(db)
    info = service.day_info(db, date(2026, 11, 16))  # Monday
    assert [(s.strftime("%H:%M"), e.strftime("%H:%M")) for s, e in info.windows] == [("09:30", "13:30"), ("14:00", "18:30")]
    assert info.working_hours == 8.5


def test_add_working_days_skips_off_days(db):
    cal(db)
    # Fri 13 Nov +1 -> Sat 14 (2nd, off) -> Sun 15 (off) -> Mon 16
    assert service.add_working_days(db, date(2026, 11, 13), 1) == date(2026, 11, 16)
    # Fri 20 Nov +1 -> Sat 21 (3rd, working)
    assert service.add_working_days(db, date(2026, 11, 20), 1) == date(2026, 11, 21)
    # Going backwards from Mon 16 -> Fri 13
    assert service.add_working_days(db, date(2026, 11, 16), -1) == date(2026, 11, 13)


def test_holiday_overrides_and_working_override(db):
    cal(db)
    db.add(Holiday(date=date(2026, 11, 17), name="Festival"))
    db.add(Holiday(date=date(2026, 11, 15), name="Special working Sunday", is_working_override=True))
    db.commit()
    assert not service.is_working_day(db, date(2026, 11, 17))
    assert service.day_info(db, date(2026, 11, 17)).holiday_name == "Festival"
    assert service.is_working_day(db, date(2026, 11, 15))


def test_eod_resolves_to_1830_company_time_in_utc(db):
    cal(db)
    # Asia/Kolkata is UTC+5:30 -> 18:30 IST == 13:00 UTC
    assert service.resolve_eod_utc(db, date(2026, 11, 20)) == datetime(2026, 11, 20, 13, 0)


def test_deadline_warning(db):
    cal(db)
    sat2 = service.resolve_eod_utc(db, date(2026, 11, 14))
    assert "off Saturday" in service.deadline_warning(db, sat2)
    assert service.deadline_warning(db, service.resolve_eod_utc(db, date(2026, 11, 16))) is None


def test_capacity_excludes_off_days_and_leave(db, seeded):
    cal(db)
    from app.seed import seed_core  # noqa: F401

    emp = db.query(Employee).first()
    # Mon 9 Nov .. Sun 15 Nov: Mon-Sat working except 2nd Sat (14th) => Mon-Fri + ... Sat 14 off => 5 days
    assert service.capacity_hours(db, emp, date(2026, 11, 9), date(2026, 11, 15)) == Decimal("42.50")
    db.add(EmployeeLeave(employee_id=emp.id, from_date=date(2026, 11, 10), to_date=date(2026, 11, 10)))
    db.commit()
    assert service.capacity_hours(db, emp, date(2026, 11, 9), date(2026, 11, 15)) == Decimal("34.00")
