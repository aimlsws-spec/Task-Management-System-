"""ADR 008: emailed one-time code on every sign-in / sign-up, and random letters+digits employee IDs."""

import re

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.modules.auth import otp
from app.modules.auth.models import LoginOtp
from app.modules.org.models import Employee

from .conftest import PASSWORD
from .helpers import API, at
from .test_org_permissions import new_emp

LOGIN = f"{API}/auth/login"
VERIFY = f"{API}/auth/verify-otp"
RESEND = f"{API}/auth/resend-otp"
CODE_RE = re.compile(r"\bsign-in code is (\d{6})\b")


@pytest.fixture()
def mails(monkeypatch):
    """OTP switched on; every code email is captured instead of sent."""
    monkeypatch.setattr(get_settings(), "otp_enabled", True)
    sent: list[tuple[str, str]] = []

    def fake(msg):
        sent.append((msg["To"], CODE_RE.search(msg["Subject"]).group(1)))
        return "log"

    monkeypatch.setattr(otp.mailer, "send_message", fake)
    return sent


def start(client, email="owner@demo.example.com", password=PASSWORD):
    r = client.post(LOGIN, json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_password_alone_gives_no_session_and_the_code_goes_to_the_registered_mail(client, mails):
    out = start(client)
    assert out["otp_required"] is True and "access_token" not in out and out["email_hint"] == "o***@demo.example.com"
    assert "tms_refresh" not in client.cookies
    assert [to for to, _ in mails] == ["owner@demo.example.com"] and re.fullmatch(r"\d{6}", mails[0][1])


def test_the_right_code_signs_in_and_works_only_once(client, mails):
    ch = start(client)["challenge"]
    r = client.post(VERIFY, json={"challenge": ch, "code": mails[0][1]})
    assert r.status_code == 200 and r.json()["access_token"]
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["user"]["email"] == "owner@demo.example.com"
    again = client.post(VERIFY, json={"challenge": ch, "code": mails[0][1]})
    assert again.status_code == 401


def test_a_wrong_password_sends_no_code(client, mails):
    r = client.post(LOGIN, json={"email": "owner@demo.example.com", "password": "Wrong@12345!"})
    assert r.status_code == 401 and r.json()["message"] == "Invalid email or password" and mails == []
    assert client.post(LOGIN, json={"email": "nobody@demo.example.com", "password": PASSWORD}).status_code == 401 and mails == []


def test_five_wrong_codes_kill_the_challenge_even_for_the_right_code(client, mails):
    ch = start(client)["challenge"]
    good = mails[0][1]
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert client.post(VERIFY, json={"challenge": ch, "code": bad}).status_code == 401
    assert client.post(VERIFY, json={"challenge": ch, "code": good}).status_code == 401
    assert client.post(LOGIN, json={"email": "owner@demo.example.com", "password": PASSWORD}).status_code == 200  # a fresh sign-in works


def test_the_code_expires(client, mails):
    at(0)
    ch = start(client)["challenge"]
    at(get_settings().otp_minutes + 1)
    assert client.post(VERIFY, json={"challenge": ch, "code": mails[0][1]}).status_code == 401


def test_a_new_sign_in_voids_the_previous_code(client, mails):
    first = start(client)["challenge"]
    old_code = mails[0][1]
    start(client)
    assert client.post(VERIFY, json={"challenge": first, "code": old_code}).status_code == 401


def test_a_code_is_bound_to_its_own_challenge(client, mails):
    a = start(client, "owner@demo.example.com")["challenge"]
    start(client, "ceo@demo.example.com")
    ceo_code = mails[1][1]
    assert client.post(VERIFY, json={"challenge": a, "code": ceo_code}).status_code == 401 or ceo_code == mails[0][1]


def test_malformed_codes_are_rejected(client, mails):
    ch = start(client)["challenge"]
    for code in ("12345", "1234567", "abcdef", ""):
        assert client.post(VERIFY, json={"challenge": ch, "code": code}).status_code == 422


def test_resend_waits_then_replaces_the_code(client, mails):
    at(0)
    ch = start(client)["challenge"]
    assert client.post(RESEND, json={"challenge": ch}).json()["code"] == "OTP_TOO_SOON"
    at(get_settings().otp_resend_seconds / 60 + 0.1)
    assert client.post(RESEND, json={"challenge": ch}).status_code == 200 and len(mails) == 2
    first, second = mails[0][1], mails[1][1]
    if first != second:
        assert client.post(VERIFY, json={"challenge": ch, "code": first}).status_code == 401
    r = client.post(VERIFY, json={"challenge": ch, "code": second})
    assert r.status_code == 200


def test_the_code_is_never_stored(client, mails, seeded):
    start(client)
    with seeded() as s:
        row = s.scalar(select(LoginOtp))
        assert mails[0][1] not in (row.code_hash, row.challenge_hash) and len(row.code_hash) == 64


def test_everyone_signs_in_with_a_code_including_the_admin(client, mails):
    for who in ("admin", "owner", "ceo", "manager", "devhead", "abc"):
        ch = start(client, f"{who}@demo.example.com")["challenge"]
        assert client.post(VERIFY, json={"challenge": ch, "code": mails[-1][1]}).status_code == 200


def test_a_mail_failure_says_so_and_gives_no_session(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "otp_enabled", True)

    def boom(msg):
        raise OSError("smtp down")

    monkeypatch.setattr(otp.mailer, "send_message", boom)
    r = client.post(LOGIN, json={"email": "owner@demo.example.com", "password": PASSWORD})
    assert r.status_code == 503 and r.json()["code"] == "OTP_EMAIL_FAILED"


def test_signup_proves_the_mailbox_with_a_code(client, mails, seeded):
    r = client.post(f"{API}/auth/signup", json={"full_name": "Sign Up Person", "email": "signup1@demo.example.com", "password": "Signup@12345!"})
    assert r.status_code == 201 and r.json()["otp_required"] is True and "access_token" not in r.json()
    assert mails[-1][0] == "signup1@demo.example.com"
    ok = client.post(VERIFY, json={"challenge": r.json()["challenge"], "code": mails[-1][1]})
    assert ok.status_code == 200 and ok.json()["access_token"]
    with seeded() as s:
        code = s.scalar(select(Employee.employee_code).where(Employee.full_name == "Sign Up Person"))
    assert re.fullmatch(r"SW-[A-Z0-9]{6}", code) and re.search(r"[A-Z]", code[3:]) and re.search(r"\d", code[3:])


def test_with_the_code_switched_off_login_is_password_only(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "otp_enabled", False)
    assert client.post(LOGIN, json={"email": "owner@demo.example.com", "password": PASSWORD}).json()["access_token"]


# ---------------- employee IDs ----------------


def test_signups_get_distinct_letter_and_digit_ids(client, seeded):
    for i in range(4):
        assert client.post(f"{API}/auth/signup", json={"full_name": f"Person {i}x", "email": f"p{i}@demo.example.com", "password": "Signup@12345!"}).status_code == 201
    with seeded() as s:
        codes = list(s.scalars(select(Employee.employee_code).where(Employee.full_name.like("Person %x"))))
    assert len(set(codes)) == 4
    for c in codes:
        assert re.fullmatch(r"SW-[A-Z0-9]{6}", c) and re.search(r"[A-Z]", c[3:]) and re.search(r"\d", c[3:])
        assert not re.fullmatch(r"EMP-?\d+", c)


def test_admin_adds_an_employee_with_a_generated_or_a_valid_custom_id(client, as_user, seeded):
    admin = as_user("admin")
    auto = new_emp(seeded, email="auto@demo.example.com")
    auto.pop("employee_code")
    r = client.post(f"{API}/employees", headers=admin, json=auto)
    assert r.status_code == 201 and re.fullmatch(r"SW-[A-Z0-9]{6}", r.json()["employee_code"])
    r = client.post(f"{API}/employees", headers=admin, json=new_emp(seeded, email="custom@demo.example.com", employee_code="sw-k7m2q9"))
    assert r.status_code == 201 and r.json()["employee_code"] == "SW-K7M2Q9"  # stored upper-case


@pytest.mark.parametrize("bad", ["EMP-001", "EMP001", "emp-0100", "12345", "ABCDEF", "7", "SW 7K2", "A-1"])
def test_basic_or_malformed_ids_are_refused(client, as_user, seeded, bad):
    r = client.post(f"{API}/employees", headers=as_user("admin"), json=new_emp(seeded, employee_code=bad))
    assert r.status_code == 422 and r.json()["code"] == "INVALID_EMPLOYEE_CODE"


def test_a_duplicate_id_is_refused(client, as_user, seeded):
    admin = as_user("admin")
    assert client.post(f"{API}/employees", headers=admin, json=new_emp(seeded, email="d1@demo.example.com", employee_code="SW-ZZ9X8Y")).status_code == 201
    r = client.post(f"{API}/employees", headers=admin, json=new_emp(seeded, email="d2@demo.example.com", employee_code="sw-zz9x8y"))
    assert r.status_code == 409 and r.json()["code"] == "EMPLOYEE_CODE_EXISTS"
