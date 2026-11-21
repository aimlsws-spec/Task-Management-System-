# Task Management System — working agreement for Claude

Source of truth: `docs/` (requirements, architecture, DB, API, roadmap). Task-level plan: `docs/11-project-plan.md`. Reference requirement IDs (FR-xxx / NFR-xxx) in commits and PRs. Deviations need an ADR in `docs/adr/`.

## Stack
Backend `backend/`: Python 3.12 (venv at `backend/.venv`, created with `uv`), FastAPI, SQLAlchemy 2.0 (sync), Pydantic v2, Alembic, **MySQL 8 is the ONLY supported database** (project decision, enforced in `core/db.make_engine`; no SQLite/Postgres/NoSQL, not even in tests). Tests run against a dedicated MySQL database whose name ends in `_test` (`TMS_TEST_DATABASE_URL`), built via the Alembic migrations. Frontend `frontend/`: React 19 + TS + Vite + Tailwind + shadcn-style components + TanStack Query + React Router. Hosting target (requested by the deployer): cPanel shared hosting, Passenger + cron (ADR 005); nothing else about hosting is in scope.

## Commands (run from `backend/`)
- Tests: `.venv/Scripts/python.exe -m pytest`
- Lint: `.venv/Scripts/python.exe -m ruff check app tests`
- Dev DB: `alembic upgrade head`, then `.venv/Scripts/python.exe -m app.cli bootstrap-admin --email you@x.com` (prompts for the password; needs `TMS_DATABASE_URL` in `backend/.env`). There is no demo data: the Admin builds the organization in the Admin panel. The sample organization used by tests is `backend/tests/demo_org.py`.
- API: `.venv/Scripts/python.exe -m uvicorn app.main:app --reload`
- Background jobs (reminders, notifications, email) run ONLY from `python -m app.jobs.run_once` (cron on cPanel; locally add `--duration 3600 --interval 5`). The API starts no threads and no WebSockets. cPanel guide: `docs/CPANEL-DEPLOY.md`, ADR 005.
- Migrations: `.venv/Scripts/python.exe -m alembic upgrade head` (MySQL via `TMS_DATABASE_URL` in `backend/.env`)

## Architecture rules
- Layers: router (HTTP only) → service (rules + transaction) → models. Authorization lives in `rbac/policy.py` + `core/deps.require`, never ad-hoc in routers.
- Authorization = permission **and** scope (`self|team|department|organization`). Out-of-scope objects return **404**, not 403.
- All stored timestamps are **naive UTC** via `app.core.clock.utcnow()` (freezable in tests). Never call `datetime.now()` directly.
- Business calendar (09:30–13:30, 14:00–18:30; Sundays + 2nd/4th Saturday off; EOD 18:30; holidays) lives only in `modules/workcal/service.py`.
- Input schemas extend `core.schemas.Strict` (`extra="forbid"`). History/audit tables are append-only.
- No hardcoded department names, role names (beyond seed data) or notification recipients.

## Never
- Weaken or delete permission tests; change `rbac/seed.py` matrix without updating `docs/03-roles-permissions.md`.
- Edit an applied Alembic migration (add a new one).
- Add dependencies without listing them in the change description.
- Commit `.env`, secrets, or `*.db` files.
- Add hosting/deployment work beyond the cPanel setup in ADR 005 unless explicitly asked.

## Workflow per task
Plan from FR IDs → write rule tests first → implement vertical slice → run tests + lint → `/code-review` (and `/security-review` for auth/permissions/uploads) → human reviews migrations/permissions → update docs.
