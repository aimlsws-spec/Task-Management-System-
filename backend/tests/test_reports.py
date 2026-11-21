"""Phase 8: dashboards, reports and exports. Scope is respected everywhere; numbers reconcile with the raw rows."""

import csv
import io

from app.modules.reports.export import safe_cell

from .helpers import ABC, API, FE, at, complete_fully, make, ok
from .test_delays import detail, explain, overdue_task, review


def get(client, as_user, who, path, **params):
    return client.get(f"{API}{path}", headers=as_user(who), params=params)


def test_dashboard_scope_follows_the_role(client, as_user, seeded):
    at(0)
    make(client, as_user, seeded, assignee=ABC)
    make(client, as_user, seeded, assignee="EMP-0009", title="HR task")  # HR1, other department
    totals = {who: get(client, as_user, who, "/dashboard").json() for who in ("owner", "ceo", "manager", "devhead", "hrhead", "abc")}
    assert totals["owner"]["totals"]["open"] == 2 and totals["ceo"]["totals"]["open"] == 2 and totals["manager"]["totals"]["open"] == 2
    assert totals["devhead"]["totals"]["open"] == 1 and totals["hrhead"]["totals"]["open"] == 1  # a head sees only their department
    assert totals["abc"]["totals"]["open"] == 1 and totals["abc"]["scope"] == "self"
    assert totals["owner"]["scope"] == "organization" and totals["devhead"]["scope"] == "department"
    assert get(client, as_user, "admin", "/dashboard").status_code in (200, 403)


def test_every_report_runs_and_respects_scope(client, as_user, seeded):
    at(0)
    make(client, as_user, seeded, assignee=ABC)
    make(client, as_user, seeded, assignee="EMP-0009", title="HR task")
    names = [r["name"] for r in get(client, as_user, "owner", "/reports").json()]
    assert {"completion", "on_time", "overdue", "extensions", "time", "rework", "blockers", "workload"} <= set(names)
    for name in names:
        for who in ("owner", "manager", "devhead", "abc"):
            r = get(client, as_user, who, f"/reports/{name}")
            assert r.status_code == 200, (name, who, r.text)
            assert set(r.json()) >= {"columns", "rows", "summary"}
    rows = get(client, as_user, "devhead", "/reports/time").json()["rows"]
    assert [r["employee"] for r in rows] == ["ABC"]  # never the HR employee
    assert get(client, as_user, "owner", "/reports/nope").status_code == 404
    assert get(client, as_user, "devhead", "/reports/completion", department_id=999999).json()["rows"] == []


def test_completion_and_on_time_reconcile_with_raw_data(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(30)
    complete_fully(client, as_user, "abc", t["id"])
    c = get(client, as_user, "owner", "/reports/completion").json()
    assert c["summary"] == {"completed": 1, "on_time": 1, "late": 0} and c["rows"][0]["employee"] == "ABC"
    o = get(client, as_user, "owner", "/reports/on_time").json()
    assert o["summary"]["on_time_vs_current_pct"] == 100.0 and o["rows"][0]["task_no"] == t["task_no"]
    assert get(client, as_user, "hrhead", "/reports/completion").json()["rows"] == []  # another department's work is invisible


def test_time_report_keeps_active_and_elapsed_apart(client, as_user, seeded):
    at(0)
    t = make(client, as_user, seeded)
    ok(client, as_user, "abc", t["id"], "start")
    at(120)
    ok(client, as_user, "abc", t["id"], "pause")
    at(24 * 60)
    row = get(client, as_user, "owner", "/reports/time").json()["rows"][0]
    assert row["active_hours"] == 2.0 and row["elapsed_hours"] > 20  # 2 h of work over a day of wall-clock time
    assert row["estimated_hours"] == 12.0


def test_overdue_report_hides_unapproved_reasons_from_leadership(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    line = get(client, as_user, "devhead", "/reports/overdue").json()["rows"][0]["explanation"]
    assert line == "awaiting approval"
    assert get(client, as_user, "ceo", "/reports/overdue").json()["rows"][0]["explanation"] == "not yet approved by the line"
    rid = detail(client, as_user, t["id"])["delay"]["items"][0]["id"]
    assert review(client, as_user, rid, "accepted", who="devhead").status_code == 200
    assert get(client, as_user, "ceo", "/reports/overdue").json()["rows"][0]["explanation"] == "approved"


def test_dashboard_decision_counts_for_leadership_only_include_escalated(client, as_user, seeded):
    t = overdue_task(client, as_user, seeded)
    explain(client, as_user, t["id"])
    assert get(client, as_user, "owner", "/dashboard").json()["needs_my_decision"] == {"explanations": 0, "overdue_without_reason": 0}
    assert get(client, as_user, "manager", "/dashboard").json()["needs_my_decision"]["explanations"] == 1


def test_export_csv_and_xlsx(client, as_user, seeded):
    at(0)
    make(client, as_user, seeded, title="=HYPERLINK(\"http://evil\")")
    r = get(client, as_user, "owner", "/reports/time/export", format="csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["employee", "tasks", "estimated_hours", "active_hours", "elapsed_hours"] and rows[1][0] == "ABC"
    r = get(client, as_user, "owner", "/reports/extensions/export", format="xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"  # a real .xlsx (zip) file
    assert get(client, as_user, "abc", "/reports/time/export", format="csv").status_code == 200  # employees export their own data
    assert get(client, as_user, "admin", "/reports/time/export").status_code == 403


def test_formula_injection_is_neutralised():
    for bad in ("=1+1", "+cmd", "-2", "@SUM(A1)", "\tx"):
        assert safe_cell(bad).startswith("'"), bad
    assert safe_cell("normal") == "normal" and safe_cell(5) == 5 and safe_cell(None) == "" and safe_cell(True) == "yes"


def test_export_is_audited(client, as_user, seeded):
    get(client, as_user, "owner", "/reports/workload/export", format="csv")
    logs = get(client, as_user, "admin", "/admin/audit-logs", action="REPORT_EXPORTED").json()
    assert logs["total"] == 1 and logs["items"][0]["after"]["format"] == "csv"


def test_employee_cannot_see_other_people_in_reports(client, as_user, seeded):
    at(0)
    make(client, as_user, seeded, assignee=ABC)
    make(client, as_user, seeded, assignee=FE, title="Other dev task")
    rows = get(client, as_user, "abc", "/reports/time").json()["rows"]
    assert [r["employee"] for r in rows] == ["ABC"]
