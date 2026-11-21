"""Self sign-up (open to any email, rate limited) and first-login onboarding: department + designation."""

import pytest
from sqlalchemy import select

from app.modules.audit.models import ActivityLog
from app.modules.org.models import Department

API = "/api/v1"
NEW = {"full_name": "Nina New", "email": "nina@example.com", "password": "Strong#Pass123"}


@pytest.fixture()
def open_signup(client):
    return client


def dept(seeded, code):
    with seeded() as s:
        return s.scalar(select(Department.id).where(Department.code == code))


def signup_and_login(client, **over):
    body = NEW | over
    assert client.post(f"{API}/auth/signup", json=body).status_code == 201
    r = client.post(f"{API}/auth/login", json={"email": body["email"], "password": body["password"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_signup_accepts_any_email_domain(open_signup):
    assert open_signup.post(f"{API}/auth/signup", json=NEW | {"email": "someone@gmail.com"}).status_code == 201


def test_signup_is_rate_limited(client):
    from app.core import ratelimit

    ratelimit.reset()
    codes = [client.post(f"{API}/auth/signup", json=NEW | {"email": f"u{i}@example.com"}).status_code for i in range(7)]
    assert codes[:5] == [201] * 5 and codes[5:] == [429, 429]


def test_signup_validates_password_and_duplicates(open_signup):
    assert open_signup.post(f"{API}/auth/signup", json=NEW | {"password": "weak"}).status_code == 422
    assert open_signup.post(f"{API}/auth/signup", json=NEW).status_code == 201
    assert open_signup.post(f"{API}/auth/signup", json=NEW).status_code == 409
    assert open_signup.post(f"{API}/auth/signup", json=NEW | {"email": "abc@demo.example.com"}).status_code == 409


def test_signup_cannot_choose_role_or_department(open_signup):
    r = open_signup.post(f"{API}/auth/signup", json=NEW | {"role_codes": ["owner"], "department_id": 1})
    assert r.status_code == 422  # unknown fields rejected: nobody can self-assign privileges


def test_new_employee_is_gated_until_onboarding_done(open_signup):
    h = signup_and_login(open_signup)
    me = open_signup.get(f"{API}/auth/me", headers=h).json()
    assert me["employee"]["status"] == "pending_setup" and me["roles"] == ["employee"]
    r = open_signup.get(f"{API}/employees", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "ONBOARDING_REQUIRED"
    assert open_signup.get(f"{API}/departments", headers=h).status_code == 200  # needed to choose from


def test_onboarding_into_developers_groups_under_developers_head(open_signup, as_user, seeded):
    h = signup_and_login(open_signup)
    r = open_signup.post(f"{API}/me/onboarding", headers=h, json={"department_id": dept(seeded, "DEV"), "designation": "AI/ML Developer"})
    assert r.status_code == 200, r.text
    dev_head = open_signup.get(f"{API}/auth/me", headers=as_user("devhead")).json()["employee"]["id"]
    assert r.json()["reports_to_id"] == dev_head and r.json()["designation"] == "AI/ML Developer"
    me = open_signup.get(f"{API}/auth/me", headers=h).json()
    assert me["employee"]["status"] == "active"
    assert open_signup.get(f"{API}/employees", headers=h).status_code == 200  # gate lifted
    # the Developers Head now sees the newcomer; the HR Head does not
    assert "Nina New" in {e["full_name"] for e in open_signup.get(f"{API}/employees", headers=as_user("devhead")).json()["items"]}
    assert "Nina New" not in {e["full_name"] for e in open_signup.get(f"{API}/employees", headers=as_user("hrhead")).json()["items"]}


def test_onboarding_into_hr_goes_to_hr_head(open_signup, as_user, seeded):
    h = signup_and_login(open_signup)
    r = open_signup.post(f"{API}/me/onboarding", headers=h, json={"department_id": dept(seeded, "HR"), "designation": "HR Executive"})
    hr_head = open_signup.get(f"{API}/auth/me", headers=as_user("hrhead")).json()["employee"]["id"]
    assert r.json()["reports_to_id"] == hr_head


def test_department_without_head_reports_to_the_manager(open_signup, as_user, seeded):
    h = signup_and_login(open_signup)
    r = open_signup.post(f"{API}/me/onboarding", headers=h, json={"department_id": dept(seeded, "SUP"), "designation": "Support Agent"})
    manager = open_signup.get(f"{API}/auth/me", headers=as_user("manager")).json()["employee"]["id"]
    assert r.json()["reports_to_id"] == manager
    assert "Nina New" in {e["full_name"] for e in open_signup.get(f"{API}/employees", headers=as_user("manager")).json()["items"]}


def test_onboarding_rejects_system_inactive_or_hidden_departments(open_signup, as_user, seeded):
    admin = as_user("admin")
    open_signup.patch(f"{API}/departments/{dept(seeded, 'SAL')}", headers=admin, json={"self_service": False})
    open_signup.patch(f"{API}/departments/{dept(seeded, 'ACC')}", headers=admin, json={"is_active": False})
    h = signup_and_login(open_signup)
    for code in ("MGMT", "UNASSIGNED", "SAL", "ACC"):
        r = open_signup.post(f"{API}/me/onboarding", headers=h, json={"department_id": dept(seeded, code), "designation": "Anything"})
        assert r.status_code == 422, code
    assert open_signup.post(f"{API}/me/onboarding", headers=h, json={"department_id": 999999, "designation": "Anything"}).status_code == 422


def test_onboarding_requires_designation_and_happens_once(open_signup, seeded):
    h = signup_and_login(open_signup)
    assert open_signup.post(f"{API}/me/onboarding", headers=h, json={"department_id": dept(seeded, "DEV"), "designation": " "}).status_code == 422
    ok = {"department_id": dept(seeded, "DEV"), "designation": "Backend Developer"}
    assert open_signup.post(f"{API}/me/onboarding", headers=h, json=ok).status_code == 200
    assert open_signup.post(f"{API}/me/onboarding", headers=h, json=ok).status_code == 409


def test_existing_employees_cannot_use_onboarding(client, as_user, seeded):
    r = client.post(f"{API}/me/onboarding", headers=as_user("abc"), json={"department_id": dept(seeded, "HR"), "designation": "x y"})
    assert r.status_code == 409


def test_signup_and_onboarding_are_audited(open_signup, seeded):
    h = signup_and_login(open_signup)
    open_signup.post(f"{API}/me/onboarding", headers=h, json={"department_id": dept(seeded, "DEV"), "designation": "Backend Developer"})
    with seeded() as s:
        actions = {a.action for a in s.scalars(select(ActivityLog))}
    assert {"SIGNUP", "ONBOARDING_COMPLETED"} <= actions


def test_admin_can_finish_a_pending_employees_setup(open_signup, as_user, seeded):
    signup_and_login(open_signup)
    admin = as_user("admin")
    pending = next(e for e in open_signup.get(f"{API}/employees", headers=admin).json()["items"] if e["full_name"] == "Nina New")
    assert pending["status"] == "pending_setup"
    r = open_signup.patch(f"{API}/employees/{pending['id']}", headers=admin, json={"department_id": dept(seeded, "HR"), "job_title": "HR Executive"})
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["reports_to_id"] is not None
