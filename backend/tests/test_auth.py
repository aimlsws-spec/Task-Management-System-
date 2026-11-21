from datetime import timedelta

from sqlalchemy import select

from app.core import clock
from app.modules.audit.models import ActivityLog
from app.modules.auth.models import RefreshToken, User

from .conftest import PASSWORD, login

XHR = {"X-Requested-With": "XMLHttpRequest"}


def test_login_success_sets_httponly_cookie(client):
    r = client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "/api/v1/auth" in cookie


def test_wrong_password_and_unknown_user_give_same_error(client):
    a = client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": "nope"})
    b = client.post("/api/v1/auth/login", json={"email": "ghost@demo.example.com", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.json()["message"] == b.json()["message"]


def test_lockout_after_five_failures_even_with_correct_password(client):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": "bad"})
    r = client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD})
    assert r.status_code == 401
    clock.freeze(clock.utcnow() + timedelta(minutes=16))
    assert client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD}).status_code == 200


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_me_returns_permission_scope_map(client, as_user):
    me = client.get("/api/v1/auth/me", headers=as_user("manager")).json()
    assert me["roles"] == ["manager"]
    assert me["permissions"]["task.deadline.edit"] == "team"
    assert "role.manage" not in me["permissions"]


def test_refresh_requires_csrf_header(client):
    client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD})
    assert client.post("/api/v1/auth/refresh").status_code == 403


def test_refresh_rotates_token(client):
    client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD})
    old_cookie = client.cookies.get("tms_refresh")
    r = client.post("/api/v1/auth/refresh", headers=XHR)
    assert r.status_code == 200
    assert client.cookies.get("tms_refresh") != old_cookie


def test_refresh_reuse_revokes_whole_family(client, seeded):
    client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD})
    stolen = client.cookies.get("tms_refresh")
    assert client.post("/api/v1/auth/refresh", headers=XHR).status_code == 200  # legit rotation
    client.cookies.clear()
    client.cookies.set("tms_refresh", stolen, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", headers=XHR).status_code == 401  # reuse detected
    with seeded() as s:
        assert all(t.revoked_at is not None for t in s.scalars(select(RefreshToken)))
        assert s.scalar(select(ActivityLog).where(ActivityLog.action == "AUTH_REFRESH_REUSE_DETECTED"))


def test_logout_revokes_refresh(client):
    client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD})
    saved = client.cookies.get("tms_refresh")
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.set("tms_refresh", saved, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", headers=XHR).status_code == 401


def test_change_password_invalidates_existing_access_tokens(client, as_user):
    h = as_user("abc")
    r = client.post("/api/v1/auth/change-password", headers=h,
                    json={"current_password": PASSWORD, "new_password": "NewSecret#2026x"})  # fmt: skip
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401  # token_version bumped
    assert login(client, "abc@demo.example.com", "NewSecret#2026x")


def test_password_policy_enforced(client, as_user):
    r = client.post("/api/v1/auth/change-password", headers=as_user("abc"),
                    json={"current_password": PASSWORD, "new_password": "short"})  # fmt: skip
    assert r.status_code == 422 and r.json()["code"] == "WEAK_PASSWORD"


def test_forgot_password_is_generic_and_reset_works(client, seeded):
    a = client.post("/api/v1/auth/forgot-password", json={"email": "abc@demo.example.com"})
    b = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@demo.example.com"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    # Pull the token the way an email would deliver it: create one directly and use it.
    from app.core.security import new_opaque_token
    from app.modules.auth.models import PasswordResetToken

    raw, hashed = new_opaque_token()
    with seeded() as s:
        uid = s.scalar(select(User.id).where(User.email == "abc@demo.example.com"))
        s.add(PasswordResetToken(user_id=uid, token_hash=hashed, expires_at=clock.utcnow() + timedelta(minutes=5)))
        s.commit()
    r = client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "BrandNew#Pass1"})
    assert r.status_code == 204
    assert client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "BrandNew#Pass2"}).status_code == 400  # single use


def test_must_change_password_gate(client, seeded):
    with seeded() as s:
        u = s.scalar(select(User).where(User.email == "abc@demo.example.com"))
        u.must_change_password = True
        s.commit()
    h = login(client, "abc@demo.example.com")
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    r = client.get("/api/v1/employees", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


def test_login_is_audited(client, seeded):
    client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": "bad"})
    client.post("/api/v1/auth/login", json={"email": "abc@demo.example.com", "password": PASSWORD})
    with seeded() as s:
        actions = {a.action for a in s.scalars(select(ActivityLog))}
    assert {"AUTH_LOGIN_FAILED", "AUTH_LOGIN"} <= actions


# ---------- dev-only per-tab sessions (several roles at once) ----------


def _enable_multi(monkeypatch):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "dev_multi_session", True)
    monkeypatch.setattr(s, "env", "dev")


def _login_body(client, name):
    r = client.post("/api/v1/auth/login", json={"email": f"{name}@demo.example.com", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


def test_multi_session_off_by_default_uses_cookie(client):
    body = _login_body(client, "abc")
    assert "refresh_token" not in body and client.cookies.get("tms_refresh")


def test_multi_session_never_active_outside_dev_env(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "dev_multi_session", True)  # env stays "test"
    assert "refresh_token" not in _login_body(client, "abc")


def test_several_roles_logged_in_at_once_stay_independent(client, monkeypatch):
    _enable_multi(monkeypatch)
    tabs = {n: _login_body(client, n) for n in ("owner", "manager", "devhead", "abc")}
    assert not client.cookies.get("tms_refresh")  # nothing shared between tabs
    for name, body in tabs.items():
        r = client.post("/api/v1/auth/refresh", headers=XHR, json={"refresh_token": body["refresh_token"]})
        assert r.status_code == 200, r.text
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
        assert me["user"]["email"] == f"{name}@demo.example.com"  # each tab keeps ITS OWN user


def test_multi_session_refresh_rotates_and_detects_reuse(client, monkeypatch):
    _enable_multi(monkeypatch)
    first = _login_body(client, "abc")["refresh_token"]
    r = client.post("/api/v1/auth/refresh", headers=XHR, json={"refresh_token": first})
    assert r.status_code == 200 and r.json()["refresh_token"] != first
    assert client.post("/api/v1/auth/refresh", headers=XHR, json={"refresh_token": first}).status_code == 401


def test_multi_session_logout_only_ends_that_tab(client, monkeypatch):
    _enable_multi(monkeypatch)
    a, b = _login_body(client, "owner")["refresh_token"], _login_body(client, "abc")["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": a}).status_code == 204
    assert client.post("/api/v1/auth/refresh", headers=XHR, json={"refresh_token": a}).status_code == 401
    assert client.post("/api/v1/auth/refresh", headers=XHR, json={"refresh_token": b}).status_code == 200
