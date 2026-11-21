"""A database that is behind the app gives a clear 503 (not a mystery 500), and server errors still carry CORS headers."""

from app.core import dbguard

ORIGIN = {"Origin": "http://localhost:5173"}


def test_an_outdated_database_answers_503_with_cors_headers(client, monkeypatch):
    monkeypatch.setattr(dbguard, "check", lambda: (False, "The database is not up to date: it is at version 0011, this app needs 0012."))
    r = client.post("/api/v1/auth/login", json={"email": "owner@demo.example.com", "password": "x"}, headers=ORIGIN)
    assert r.status_code == 503 and r.json()["code"] == "DB_OUTDATED" and "0011" in r.json()["message"]
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    h = client.get("/healthz")
    assert h.status_code == 200  # health check itself never fails


def test_healthz_reports_the_database_state(client):
    assert client.get("/healthz").json()["database"] == "ok"


def test_an_unexpected_error_is_json_and_readable_cross_origin(client, monkeypatch):
    from app.modules.auth import service

    def boom(*a, **k):
        raise RuntimeError("table login_otps does not exist")

    monkeypatch.setattr(service, "check_credentials", boom)
    monkeypatch.setattr(service, "login", boom)
    r = client.post("/api/v1/auth/login", json={"email": "owner@demo.example.com", "password": "x"}, headers=ORIGIN)
    assert r.status_code == 500 and r.json()["code"] in ("INTERNAL_ERROR", "INTERNAL") and r.json().get("request_id")
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
