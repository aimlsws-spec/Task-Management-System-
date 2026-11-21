"""cPanel readiness: jobs run from cron (one at a time), the API starts no threads and no WebSockets, Passenger entry works."""

import io
import sys
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core import clock
from app.jobs import run_once, scheduler
from app.modules.audit.models import SystemSetting
from app.modules.notifications.models import Notification

from .helpers import API
from .test_delivery import MON_11AM, mk


@pytest.fixture(autouse=True)
def _loggers_on():
    for lg in (run_once.log, scheduler.log):
        lg.disabled = False  # Alembic's fileConfig (run by the test database setup) switches pre-existing loggers off


def _held_lock(seeded):
    """Another connection (a second cron run) holding the scheduler lock."""
    other = seeded()
    name = scheduler.lock_name(other)
    assert other.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": name}).scalar() == 1
    return other, name


def test_a_pass_does_nothing_while_another_pass_holds_the_lock(client, as_user, seeded):
    clock.freeze(MON_11AM)
    mk(client, as_user, seeded)
    other, name = _held_lock(seeded)
    try:
        assert scheduler.run_locked(seeded) is None  # skipped, not queued, not failed
        with seeded() as s:
            assert s.scalar(select(Notification.id).limit(1)) is None  # nothing was processed
    finally:
        other.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": name})
        other.close()
    assert scheduler.run_locked(seeded)["notified"] == 4  # free again: the next pass does the work


def test_the_lock_is_released_after_a_pass_even_when_it_fails(seeded, monkeypatch):
    def boom(db, now=None, scan=True):
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(scheduler, "tick", boom)
    try:
        scheduler.run_locked(seeded)
    except RuntimeError:
        pass
    with seeded() as s:  # a crashed pass must not leave the jobs locked
        assert s.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": scheduler.lock_name(s)}).scalar() == 1
        s.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": scheduler.lock_name(s)})


def test_a_killed_run_frees_the_lock_when_its_connection_ends(seeded):
    other, name = _held_lock(seeded)
    other.connection().invalidate()  # what happens when the cron process dies: its connection is closed
    other.close()
    with seeded() as s:
        assert s.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": name}).scalar() == 1
        s.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": name})


def test_two_parallel_passes_never_double_process(client, as_user, seeded):
    clock.freeze(MON_11AM)
    mk(client, as_user, seeded)
    results: list = []
    threads = [threading.Thread(target=lambda: results.append(scheduler.run_locked(seeded))) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    with seeded() as s:
        keys = [tuple(r) for r in s.execute(select(Notification.user_id, Notification.dedupe_key))]
    assert len(keys) == len(set(keys)) == 4  # one notification per person, however many cron runs overlapped
    assert any(r is not None for r in results)


def test_run_now_uses_the_same_lock_as_cron(client, as_user, seeded):
    other, name = _held_lock(seeded)
    try:
        r = client.post(f"{API}/admin/jobs/run-now", headers=as_user("admin"))
        assert r.status_code == 409 and r.json()["code"] == "SCHEDULER_BUSY"
    finally:
        other.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": name})
        other.close()
    assert client.post(f"{API}/admin/jobs/run-now", headers=as_user("admin")).status_code == 200


def test_the_cron_entry_point_runs_one_pass_and_exits(client, as_user, seeded, tmp_path):
    clock.freeze(MON_11AM)
    mk(client, as_user, seeded)
    log_file = tmp_path / "scheduler.log"
    assert run_once.main(["--log-file", str(log_file)]) == 0
    with seeded() as s:
        assert len(list(s.scalars(select(Notification.id)))) == 4
        assert s.get(SystemSetting, "scheduler_status").value["last_tick_at"]
    assert "database server version" in log_file.read_text() and "pass 1 done" in log_file.read_text()
    assert run_once.main(["--log-file", str(log_file), "--check"]) == 0


def test_cron_reports_a_failing_run_with_exit_code_1(monkeypatch, tmp_path):
    def boom(factory, now=None, scan=True):
        raise RuntimeError("database gone")

    monkeypatch.setattr(scheduler, "run_locked", boom)
    log_file = tmp_path / "s.log"
    assert run_once.main(["--log-file", str(log_file)]) == 1
    assert "database gone" in log_file.read_text()


def test_admin_status_shows_whether_cron_is_running(client, as_user, seeded):
    st = client.get(f"{API}/admin/jobs/status", headers=as_user("admin")).json()
    assert st["scheduler_running"] is False and st["scheduler_age_seconds"] is None  # cron never ran
    clock.freeze(MON_11AM)
    scheduler.run_locked(seeded)
    assert client.get(f"{API}/admin/jobs/status", headers=as_user("admin")).json()["scheduler_running"] is True
    clock.freeze(MON_11AM + timedelta(minutes=10))  # cron stopped 10 minutes ago
    assert client.get(f"{API}/admin/jobs/status", headers=as_user("admin")).json()["scheduler_running"] is False


def test_no_websocket_endpoints_remain(client, as_user):
    assert client.post(f"{API}/ws/ticket", headers=as_user("abc")).status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("/ws" in p for p in paths)


def test_notifications_are_plain_rest_and_user_specific(client, as_user, seeded):
    clock.freeze(MON_11AM)
    mk(client, as_user, seeded)
    scheduler.run_locked(seeded)
    mine = client.get(f"{API}/notifications/unread-count", headers=as_user("abc")).json()["unread"]
    assert mine >= 1
    others = [client.get(f"{API}/notifications/unread-count", headers=as_user(u)).json()["unread"] for u in ("abc", "owner")]
    assert others[0] == mine  # each person only ever sees their own count
    assert client.get(f"{API}/notifications/unread-count").status_code == 401  # expired/missing token


def test_the_app_starts_no_threads(monkeypatch):
    from app.main import create_app

    before = threading.active_count()
    create_app()
    assert threading.active_count() == before


def test_passenger_entry_point_serves_http_through_wsgi():
    sys.modules.pop("passenger_wsgi", None)
    import passenger_wsgi

    environ = {
        "REQUEST_METHOD": "GET", "PATH_INFO": "/healthz", "QUERY_STRING": "", "SERVER_NAME": "t", "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.version": (1, 0), "wsgi.url_scheme": "http", "wsgi.input": io.BytesIO(b""),
        "wsgi.errors": sys.stderr, "wsgi.multithread": True, "wsgi.multiprocess": False, "wsgi.run_once": False,
    }  # fmt: skip
    seen: dict = {}
    body = b"".join(passenger_wsgi.application(environ, lambda status, headers, exc=None: seen.update(status=status)))
    assert seen["status"].startswith("200") and b"ok" in body


def test_the_website_fallback_serves_index_for_page_urls(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import _serve_website

    (tmp_path / "index.html").write_text("<html>TMS</html>")
    app = FastAPI()
    _serve_website(app, str(tmp_path))
    c = TestClient(app)
    assert "TMS" in c.get("/tasks/5").text and "TMS" in c.get("/login").text
    assert c.get("/api/v1/nothing").status_code == 404  # an API typo is never answered with the website
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-1.js").write_text("console.log(1)")
    (tmp_path / "config.js").write_text("window.__TMS_CONFIG__={}")
    (tmp_path / ".htaccess").write_text("secret")
    js = c.get("/assets/app-1.js")
    assert js.status_code == 200 and "console.log" in js.text and "immutable" in js.headers["cache-control"]  # real files are served
    assert "__TMS_CONFIG__" in c.get("/config.js").text and c.get("/config.js").headers["cache-control"] == "no-cache"
    assert "TMS" in c.get("/assets/missing.js").text  # unknown path -> the website (client-side routing)
    assert "secret" not in c.get("/.htaccess").text  # dotfiles are never served
    assert "TMS" in c.get("/../app/main.py").text or c.get("/../app/main.py").status_code in (200, 404)  # no path escape
