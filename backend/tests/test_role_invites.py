"""Admin-managed role emails (Owner / CEO / ...), department heads granted by the Admin, and no audit log for Owner/CEO.

Decision (ADR 002): the Admin registers an email with a role; whoever signs up with that exact email receives the
role automatically. Only the Admin can manage these emails. Open sign-up still gives plain Employees."""

import pytest
from sqlalchemy import select

from app.modules.org.models import Department, Employee

API = "/api/v1"
PW = "Strong#Pass123"


def invite(client, as_user, email, role, who="admin"):
    return client.post(f"{API}/role-invites", headers=as_user(who), json={"email": email, "role_code": role})


def signup_login(client, email, name="New Person"):
    assert client.post(f"{API}/auth/signup", json={"full_name": name, "email": email, "password": PW}).status_code == 201
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def me(client, h):
    return client.get(f"{API}/auth/me", headers=h).json()


def dept_id(seeded, code):
    with seeded() as s:
        return s.scalar(select(Department.id).where(Department.code == code))


# ---------- role emails ----------
@pytest.mark.parametrize("role", ["owner", "ceo", "manager"])
def test_invited_email_signs_up_straight_into_the_role(client, as_user, seeded, role):
    assert invite(client, as_user, "boss@company.example", role).status_code == 201
    h = signup_login(client, "boss@company.example")
    m = me(client, h)
    assert m["roles"] == [role]
    assert m["employee"]["status"] == "active"  # no onboarding gate for management roles
    assert m["employee"]["department_id"] == dept_id(seeded, "MGMT")
    assert "task.assign" in m["permissions"]
    assert client.get(f"{API}/employees", headers=h).status_code == 200


def test_email_match_ignores_case_and_spaces(client, as_user):
    assert invite(client, as_user, "  Boss@Company.Example ", "ceo").status_code == 201
    assert me(client, signup_login(client, "BOSS@company.example"))["roles"] == ["ceo"]


def test_uninvited_signup_is_still_a_plain_employee(client, as_user):
    invite(client, as_user, "boss@company.example", "owner")
    m = me(client, signup_login(client, "someone.else@company.example"))
    assert m["roles"] == ["employee"] and m["employee"]["status"] == "pending_setup"


def test_invited_ceo_reports_to_the_owner(client, as_user, seeded):
    invite(client, as_user, "ceo2@company.example", "ceo")
    ceo = me(client, signup_login(client, "ceo2@company.example"))["employee"]["id"]
    rows = {e["id"]: e for e in client.get(f"{API}/employees", params={"page_size": 200}, headers=as_user("admin")).json()["items"]}
    with seeded() as s:
        owner_id = s.scalar(select(Employee.id).where(Employee.employee_code == "EMP-0001"))
    assert rows[ceo]["reports_to_id"] == owner_id


def test_each_email_is_claimed_once(client, as_user):
    invite(client, as_user, "boss@company.example", "owner")
    signup_login(client, "boss@company.example")
    listed = client.get(f"{API}/role-invites", headers=as_user("admin")).json()
    assert listed[0]["email"] == "boss@company.example" and listed[0]["claimed"] is True
    assert client.post(f"{API}/auth/signup", json={"full_name": "Dup", "email": "boss@company.example", "password": PW}).status_code == 409


def test_cannot_invite_admin_role_or_unknown_role(client, as_user):
    assert invite(client, as_user, "a@company.example", "admin").status_code == 422
    assert invite(client, as_user, "a@company.example", "nonsense").status_code == 422


def test_duplicate_invite_is_refused(client, as_user):
    assert invite(client, as_user, "boss@company.example", "owner").status_code == 201
    assert invite(client, as_user, "BOSS@company.example", "ceo").status_code == 409


def test_inviting_an_existing_user_grants_the_role_now(client, as_user):
    h = signup_login(client, "early@company.example")
    assert me(client, h)["roles"] == ["employee"]
    assert invite(client, as_user, "early@company.example", "ceo").status_code == 201
    # sessions were revoked so the new permissions apply at the next login
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401
    r = client.post(f"{API}/auth/login", json={"email": "early@company.example", "password": PW})
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert "ceo" in me(client, h2)["roles"]


def test_revoking_an_unclaimed_invite_stops_it(client, as_user):
    iid = invite(client, as_user, "boss@company.example", "owner").json()["id"]
    assert client.delete(f"{API}/role-invites/{iid}", headers=as_user("admin")).status_code == 204
    assert me(client, signup_login(client, "boss@company.example"))["roles"] == ["employee"]


def test_claimed_invite_cannot_be_deleted(client, as_user):
    iid = invite(client, as_user, "boss@company.example", "owner").json()["id"]
    signup_login(client, "boss@company.example")
    assert client.delete(f"{API}/role-invites/{iid}", headers=as_user("admin")).status_code == 409


@pytest.mark.parametrize("who", ["ceo", "manager", "devhead", "abc"])
def test_only_admin_and_owner_manage_role_emails(client, as_user, who):
    h = as_user(who)
    assert client.get(f"{API}/role-invites", headers=h).status_code == 403
    assert invite(client, as_user, "x@company.example", "ceo", who=who).status_code == 403
    assert client.delete(f"{API}/role-invites/1", headers=h).status_code == 403


def test_owner_can_manage_role_emails(client, as_user):
    h = as_user("owner")
    assert client.get(f"{API}/role-invites", headers=h).status_code == 200


# ---------- department heads ----------
def roles_of(client, as_user, emp_id):
    rows = client.get(f"{API}/employees", params={"page_size": 200}, headers=as_user("admin")).json()["items"]
    return next(e["roles"] for e in rows if e["id"] == emp_id)


def test_naming_a_department_head_gives_that_person_the_head_role(client, as_user, seeded):
    abc = me(client, as_user("abc"))["employee"]["id"]
    r = client.put(f"{API}/departments/{dept_id(seeded, 'DEV')}/head", headers=as_user("admin"), json={"head_employee_id": abc, "regroup_members": True})
    assert r.status_code == 200, r.text
    assert "department_head" in roles_of(client, as_user, abc)
    m = me(client, as_user("abc"))  # fresh login picks up the new authority
    assert m["permissions"]["task.assign"] == "department"


def test_replaced_head_loses_the_head_role_but_keeps_their_job(client, as_user, seeded):
    devhead = me(client, as_user("devhead"))["employee"]["id"]
    abc = me(client, as_user("abc"))["employee"]["id"]
    client.put(f"{API}/departments/{dept_id(seeded, 'DEV')}/head", headers=as_user("admin"), json={"head_employee_id": abc})
    assert "department_head" not in roles_of(client, as_user, devhead)
    assert roles_of(client, as_user, devhead)  # still has a role (employee)
    assert client.post(f"{API}/auth/login", json={"email": "devhead@demo.example.com", "password": "Demo@12345!"}).status_code == 200


def test_head_of_two_departments_keeps_the_role_when_one_is_reassigned(client, as_user, seeded):
    devhead = me(client, as_user("devhead"))["employee"]["id"]
    abc = me(client, as_user("abc"))["employee"]["id"]
    client.put(f"{API}/departments/{dept_id(seeded, 'SUP')}/head", headers=as_user("admin"), json={"head_employee_id": devhead})
    client.put(f"{API}/departments/{dept_id(seeded, 'DEV')}/head", headers=as_user("admin"), json={"head_employee_id": abc})
    assert "department_head" in roles_of(client, as_user, devhead)  # still heads Support


def test_clearing_a_head_removes_the_role_from_the_old_head(client, as_user, seeded):
    devhead = me(client, as_user("devhead"))["employee"]["id"]
    client.put(f"{API}/departments/{dept_id(seeded, 'DEV')}/head", headers=as_user("admin"), json={"head_employee_id": None})
    assert "department_head" not in roles_of(client, as_user, devhead)


def test_naming_a_manager_as_head_does_not_downgrade_them(client, as_user, seeded):
    mgr = me(client, as_user("manager"))["employee"]["id"]
    client.put(f"{API}/departments/{dept_id(seeded, 'SUP')}/head", headers=as_user("admin"), json={"head_employee_id": mgr})
    assert "manager" in roles_of(client, as_user, mgr)


# ---------- audit log: Admin and Owner have it, CEO does not ----------
def test_ceo_has_no_audit_log(client, as_user):
    assert "audit.view" not in me(client, as_user("ceo"))["permissions"]
    assert client.get(f"{API}/admin/audit-logs", headers=as_user("ceo")).status_code == 403


def test_admin_and_owner_have_the_audit_log(client, as_user):
    assert client.get(f"{API}/admin/audit-logs", headers=as_user("admin")).status_code == 200
    assert client.get(f"{API}/admin/audit-logs", headers=as_user("owner")).status_code == 200


# ---------- emails ----------
def emails(seeded, to):
    from app.modules.notifications.models import EmailLog

    with seeded() as s:
        return list(s.scalars(select(EmailLog).where(EmailLog.to_email == to).order_by(EmailLog.id)))


def test_registering_a_role_email_sends_that_person_an_invitation(client, as_user, seeded):
    invite(client, as_user, "boss@company.example", "owner")
    mails = emails(seeded, "boss@company.example")
    assert len(mails) == 1 and mails[0].status == "queued" and mails[0].urgent
    assert "Owner" in mails[0].subject and "/signup" in mails[0].body_text and "boss@company.example" in mails[0].body_text


def test_a_registered_person_with_an_account_is_told_to_sign_in_again(client, as_user, seeded):
    signup_login(client, "early@company.example")
    invite(client, as_user, "early@company.example", "ceo")
    mails = [m for m in emails(seeded, "early@company.example") if "CEO" in m.subject]  # (the other mail is the sign-up welcome)
    assert len(mails) == 1 and "/login" in mails[0].body_text


def test_new_signup_notifies_every_owner_in_app_and_by_email(client, as_user, seeded):
    from app.modules.notifications.models import Notification
    from tests.test_notifications import relay

    signup_login(client, "nina@company.example", name="Nina New")
    relay(seeded)
    owner_h = as_user("owner")
    items = client.get(f"{API}/notifications", headers=owner_h).json()["items"]
    hit = [n for n in items if n["event_type"] == "EMPLOYEE_SIGNED_UP"]
    assert len(hit) == 1 and "Nina New" in hit[0]["body"] and "nina@company.example" in hit[0]["body"]
    assert emails(seeded, "owner@demo.example.com")  # and an email is queued for them
    assert not [n for n in client.get(f"{API}/notifications", headers=as_user("abc")).json()["items"] if n["event_type"] == "EMPLOYEE_SIGNED_UP"]
    with seeded() as s:
        assert s.scalar(select(Notification.id).where(Notification.event_type == "EMPLOYEE_SIGNED_UP"))


def test_an_invited_owner_signing_up_is_not_told_about_themselves(client, as_user, seeded):
    from tests.test_notifications import relay

    invite(client, as_user, "boss@company.example", "owner")
    h = signup_login(client, "boss@company.example")
    relay(seeded)
    assert not [n for n in client.get(f"{API}/notifications", headers=h).json()["items"] if n["event_type"] == "EMPLOYEE_SIGNED_UP"]


# ---------- every account change is emailed ----------
def new_employee(client, as_user, seeded, email="newbie@company.example", role="employee"):
    r = client.post(f"{API}/employees", headers=as_user("admin"), json={
        "email": email, "full_name": "Newbie Person", "employee_code": "SW-R4T8N3", "department_id": dept_id(seeded, "DEV"),
        "temp_password": "Temp#Pass12345", "role_codes": [role]})
    assert r.status_code == 201, r.text
    return r.json()


def test_an_employee_added_by_the_admin_is_emailed_how_to_sign_in(client, as_user, seeded):
    new_employee(client, as_user, seeded)
    mails = emails(seeded, "newbie@company.example")
    assert len(mails) == 1 and mails[0].urgent and "/login" in mails[0].body_text
    assert "Employee" in mails[0].subject and "Temp#Pass12345" not in mails[0].body_text + mails[0].body_html  # never mail a password


def test_changing_someones_role_emails_them(client, as_user, seeded):
    emp = new_employee(client, as_user, seeded)
    r = client.patch(f"{API}/employees/{emp['id']}", headers=as_user("admin"), json={"role_codes": ["manager"]})
    assert r.status_code == 200, r.text
    assert any("Manager" in m.subject for m in emails(seeded, "newbie@company.example"))
    r = client.put(f"{API}/users/{emp['user_id']}/roles", headers=as_user("admin"), json={"role_codes": ["department_head"]})
    assert r.status_code == 200, r.text
    assert any("Department Head" in m.subject for m in emails(seeded, "newbie@company.example"))


def test_naming_a_department_head_emails_the_new_head(client, as_user, seeded):
    abc = me(client, as_user("abc"))["employee"]["id"]
    client.put(f"{API}/departments/{dept_id(seeded, 'DEV')}/head", headers=as_user("admin"), json={"head_employee_id": abc})
    mails = emails(seeded, "abc@demo.example.com")
    assert len(mails) == 1 and "Developers" in mails[0].subject + mails[0].body_text


def test_signing_up_sends_a_welcome_email(client, as_user, seeded):
    signup_login(client, "nina@company.example", name="Nina New")
    mails = emails(seeded, "nina@company.example")
    assert len(mails) == 1 and "Welcome" in mails[0].subject and "/login" in mails[0].body_text


def test_the_admin_is_told_about_new_sign_ups_too(client, as_user, seeded):
    from tests.test_notifications import relay

    signup_login(client, "nina@company.example", name="Nina New")
    relay(seeded)
    assert [n for n in client.get(f"{API}/notifications", headers=as_user("admin")).json()["items"] if n["event_type"] == "EMPLOYEE_SIGNED_UP"]
    assert emails(seeded, "admin@demo.example.com")


def test_an_invitation_can_be_sent_again_until_it_is_claimed(client, as_user, seeded):
    iid = invite(client, as_user, "boss@company.example", "owner").json()["id"]
    r = client.post(f"{API}/role-invites/{iid}/resend", headers=as_user("admin"))
    assert r.status_code == 200, r.text
    assert len(emails(seeded, "boss@company.example")) == 2
    signup_login(client, "boss@company.example")
    assert client.post(f"{API}/role-invites/{iid}/resend", headers=as_user("admin")).status_code == 409
    assert client.post(f"{API}/role-invites/{iid}/resend", headers=as_user("owner")).status_code == 409
    for who in ("ceo", "abc"):
        assert client.post(f"{API}/role-invites/{iid}/resend", headers=as_user(who)).status_code == 403
