# TMS – Local Setup & Run Guide (Windows)

Task Management System: FastAPI + SQLAlchemy + MySQL backend, React 19 + Vite frontend.

## 1. Prerequisites
| Tool | Version | Check |
|---|---|---|
| Python | 3.12 or 3.13 | `python --version` |
| Node.js / npm | 20+ | `node -v` |
| MySQL Server | 8+ (9.5 works) | Windows service `MySQL95` must be **Running** |

MySQL is the only supported database (no SQLite/Postgres).

## 2. One-time setup

### 2.1 Create the databases and app user 
In PowerShell:
```powershell
$env:MYSQL_PWD = '<your MySQL root password>'
& 'C:\Program Files\MySQL\MySQL Server 9.5\bin\mysql.exe' -uroot -e "
CREATE DATABASE IF NOT EXISTS tms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS tms_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'tms_user'@'localhost' IDENTIFIED BY '<password from backend/.env>';
GRANT ALL ON tms.* TO 'tms_user'@'localhost';
GRANT ALL ON tms_test.* TO 'tms_user'@'localhost';"
Remove-Item Env:MYSQL_PWD
```
(Reference script: `backend/scripts/mysql_setup.sql`.)

### 2.2 Backend configuration
`backend/.env` already exists (git-ignored). Its `TMS_DATABASE_URL` / `TMS_TEST_DATABASE_URL` must use the `tms_user` password you created above. Template: `backend/.env.example`.
Note: `.env` also holds SMTP settings. For local work without sending real mail, set `TMS_EMAIL_BACKEND=log`.

### 2.3 Backend install, migrate, seed
```powershell
cd D:\TMS\project\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.cli bootstrap-admin --email you@yourcompany.com
```
Run `alembic upgrade head` again after pulling updates. The system starts **empty**: `bootstrap-admin` creates the Admin account (it asks for a password) and nothing else.

### 2.4 Frontend install
```powershell
cd D:\TMS\project\frontend
npm install
```

## 3. Run the project (two terminals)

**Terminal 1 – API** (http://localhost:8000, docs at http://localhost:8000/docs)
```powershell
cd D:\TMS\project\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**Terminal 2 – UI** (http://localhost:5173, proxies `/api` to port 8000)
```powershell
cd D:\TMS\project\frontend
npm run dev
```
Open http://localhost:5173.

## 4. First run: build the organization (as Admin)
There is no demo data. Sign in at http://localhost:5173 with the Admin account you created, then:
1. **Departments**: add your departments. Each one appears in the list new employees choose from at sign-up.
2. **Role emails**: register the email of your Owner, CEO (and Manager). Send them the sign-up link; when they sign up with that exact email they get the role and join Management automatically.
3. Employees **sign up** themselves at `/signup`, then pick their department and designation.
4. **Departments > Head**: choose each department's head. This also gives them the Department Head role (they sign in again to use it) and, with "move members" ticked, puts the department under them.
5. **Hierarchy** / **Employees**: adjust reporting lines or roles at any time.

Owner and CEO do not see the Audit log; only the Admin does.

## 5. Useful commands (from `backend/`)
```powershell
.\.venv\Scripts\python.exe -m pytest                  # tests (use the tms_test DB)
.\.venv\Scripts\python.exe -m ruff check app tests    # lint
.\.venv\Scripts\python.exe -m app.cli bootstrap-admin --email you@x.com --password '...'
.\.venv\Scripts\python.exe -m app.cli send-test-email --to you@x.com
```
Frontend: `npm run typecheck`, `npm run build`.

## 6. Troubleshooting
- **Access denied for tms_user** – the password in `backend/.env` doesn't match MySQL; re-run `ALTER USER 'tms_user'@'localhost' IDENTIFIED BY '...'`.
- **Can't connect to MySQL** – start the service: `Start-Service MySQL95` (admin PowerShell).
- **Port 8000/5173 busy** – stop the other process or change the port (update `TMS_CORS_ORIGINS` and `vite.config.ts` proxy).
- **Emails fail** – SMTP creds in `.env` are real; set `TMS_EMAIL_BACKEND=log` for local dev.
- Background jobs run inside the API process (`TMS_INLINE_JOBS=true`); no Redis/Docker needed.

## 7. Email that works after deployment
Everything is built to send email correctly anywhere; it needs three settings in `backend/.env`:
1. `TMS_APP_BASE_URL` = the public address of the site (for example `https://tasks.yourcompany.com`). Every email link ("Open the task", "Create your account") is built from it. The Admin page *Notifications & Jobs* shows a warning while it still says `localhost`.
2. `TMS_EMAIL_BACKEND=smtp` with `TMS_SMTP_HOST`, `TMS_SMTP_PORT`, `TMS_SMTP_SECURITY` (`ssl` for 465, `starttls` for 587), `TMS_SMTP_USER`, `TMS_SMTP_PASSWORD`.
3. `TMS_EMAIL_FROM` should be an address on the same domain as the mailbox (for example `SeaWind Tasks <tasks@yourcompany.com>`), and that domain's DNS should have **SPF**, **DKIM** and **DMARC** records for the mail provider. Without them many inboxes file system mail as spam. Each email carries a Date, a Message-ID and an `Auto-Submitted` header.
Check delivery with `python -m app.cli send-test-email --to you@yourcompany.com`. Failed emails are retried with backoff and shown (with the reason) under *Notifications & Jobs*.
