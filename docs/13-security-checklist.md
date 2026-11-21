# Document 13 — Security & Hardening Checklist (Phase 9)

Status after Phase 9. "Test" names the automated evidence.

| Area | Control | Evidence |
|---|---|---|
| Authentication | argon2id hashes, lockout, refresh rotation + reuse detection, rate limits | `test_auth.py` |
| Authorization | RBAC × scope on every endpoint; out-of-scope = 404 | `test_permission_matrix.py` (one test per endpoint × role, incl. reports/dashboard/ownership) |
| Confidentiality of delay reasons | CEO/Owner cannot read, list, review, or see counts of unreleased reasons | `test_delays.py` (leadership tests), `test_reports.py`, `test_notifications.py` |
| Peer assignment | Heads may assign to other Heads only; not outside department, not upward, employees cannot | `test_head_workflow.py` |
| Integrity | Original deadline immutable; explanations, ownership, history append-only | `test_deadlines.py`, `test_delays.py` |
| Injection | SQLAlchemy parameterised queries only; user text escaped in email/HTML | `test_comments.py`, `test_delivery.py` |
| CSV/Excel injection | Cells starting `= + - @ TAB CR` are prefixed; formulas never stored | `test_reports.py::test_formula_injection_is_neutralised` |
| Uploads | allow-list, magic-byte check, 25 MB cap, random storage names, authorization on every download | `test_tasks.py` |
| Data export | Audited (`REPORT_EXPORTED`), capped at 50,000 rows, scoped | `test_reports.py::test_export_is_audited` |
| Secrets | `.env` git-ignored; startup refuses weak secret / dev multi-session outside dev | `app/main.py` |
| Transport headers | `X-Content-Type-Options`, `Cache-Control: no-store` | `app/main.py` |
| Dependencies | `openpyxl` added in Phase 8 (listed in `pyproject.toml`); run `pip-audit` / `npm audit` before release | manual |

## Known limits / before go-live (hosting phase, out of scope)
TLS and secure cookies (`TMS_COOKIE_SECURE=true`), backups, monitoring, optional MFA for Owner/CEO, rotate the SMTP password stored in `backend/.env`, set `TMS_APP_BASE_URL`.
