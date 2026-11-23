"""Sample organization used ONLY by the test-suite (never by the product): Owner > CEO > Manager > heads > employees.
The real system starts empty: `python -m app.cli bootstrap-admin`, then the Admin builds everything in the Admin panel."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.org.models import Department, Employee
from app.modules.org.service import set_manager
from app.seed import create_user_employee, seed_core

DEMO_DEPARTMENTS = [("Developers", "DEV"), ("HR", "HR"), ("Marketing", "MKT"), ("Support", "SUP"), ("Sales", "SAL"), ("Accounts", "ACC")]


def seed_demo(db: Session, password: str = "Demo@12345!") -> None:
    """Sample organization from the plan: Owner > CEO > Manager > heads > employees (ABC = AI/ML dev)."""
    seed_core(db)
    for name, code in DEMO_DEPARTMENTS:
        if db.scalar(select(Department.id).where(Department.code == code)) is None:
            db.add(Department(name=name, code=code))
    db.flush()
    mk = lambda *a, **k: create_user_employee(db, *a, **k)  # noqa: E731
    if not db.scalar(select(User.id).where(User.email == "admin@demo.example.com")):  # also upgrades older demo data
        admin = mk("admin@demo.example.com", password, "Demo Admin", "EMP-0000", "MGMT", "admin", "System Administrator")
    else:
        admin = db.scalar(select(Employee).join(User, User.id == Employee.user_id).where(User.email == "admin@demo.example.com"))
        admin.can_receive_tasks = False
    if db.scalar(select(User.id).where(User.email == "owner@demo.example.com")):
        return
    owner = mk("owner@demo.example.com", password, "Demo Owner", "EMP-0001", "MGMT", "owner", "Owner")
    ceo = mk("ceo@demo.example.com", password, "Demo CEO", "EMP-0002", "MGMT", "ceo", "CEO")
    mgr = mk("manager@demo.example.com", password, "Demo Manager", "EMP-0003", "MGMT", "manager", "Manager")
    dev_head = mk("devhead@demo.example.com", password, "Developers Head", "EMP-0004", "DEV", "department_head", "Developers Head")
    hr_head = mk("hrhead@demo.example.com", password, "HR Head", "EMP-0005", "HR", "department_head", "HR Head")
    mkt_head = mk("mktghead@demo.example.com", password, "Marketing Head", "EMP-0006", "MKT", "department_head", "Marketing Head")
    abc = mk("abc@demo.example.com", password, "ABC", "EMP-0007", "DEV", "employee", "AI/ML Developer")
    fe = mk("frontend@demo.example.com", password, "Frontend Dev", "EMP-0008", "DEV", "employee", "Frontend Developer")
    hr1 = mk("hr1@demo.example.com", password, "HR Executive", "EMP-0009", "HR", "employee", "HR Executive")
    mk1 = mk("marketing1@demo.example.com", password, "Marketing Executive", "EMP-0010", "MKT", "employee", "Marketing Executive")
    sup = mk("support1@demo.example.com", password, "Support Agent", "EMP-0011", "SUP", "employee", "Support Employee")
    sal = mk("sales1@demo.example.com", password, "Sales Executive", "EMP-0012", "SAL", "employee", "Sales Employee")
    acc = mk("accounts1@demo.example.com", password, "Accountant", "EMP-0013", "ACC", "employee", "Accounts Employee")

    class _Actor:  # minimal stand-in for audit/created_by during seeding
        rank = 110
        can_access_company = staticmethod(lambda cid: True)

        class user:  # noqa: N801
            id = admin.user_id

    for emp, boss in [
        (ceo, owner), (mgr, ceo), (dev_head, mgr), (hr_head, mgr), (mkt_head, mgr),
        (abc, dev_head), (fe, dev_head), (hr1, hr_head), (mk1, mkt_head),
        (sup, mgr), (sal, mgr), (acc, mgr),
    ]:  # fmt: skip
        set_manager(db, _Actor, emp.id, boss.id, request=None, audit_it=False)  # type: ignore[arg-type]
    for dept_code, head in (("DEV", dev_head), ("HR", hr_head), ("MKT", mkt_head)):
        db.scalar(select(Department).where(Department.code == dept_code)).head_employee_id = head.id
    db.flush()
