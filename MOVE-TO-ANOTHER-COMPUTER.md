# Move the TMS project to another computer (Windows)

This package contains the full source code, `backend/.env` (real settings and passwords) and `tms_db_dump.sql` (the whole `tms` database: users, tasks, history, settings, notification rules, everything as it was when the zip was made).
Keep this zip private: `.env` holds the database password, the JWT secret key and the company mailbox password.

Time needed: about 20 minutes.

## 1. Install the prerequisites
| Tool | Version | Check |
|---|---|---|
| Python | 3.12 or 3.13 | `python --version` |
| Node.js (with npm) | 20 or newer | `node -v` |
| MySQL Server | 8.0 or newer (9.x works) | `mysql --version` |

Install MySQL as a Windows service, remember the **root password** you choose, and make sure the service is running (`Get-Service MySQL*`). MySQL is the only supported database.

## 2. Unzip
Unzip anywhere, for example `D:\TMS`. You get a folder `TMS-project` containing `backend`, `frontend`, `docs`, `SETUP.md` and `tms_db_dump.sql`. The paths below assume `D:\TMS\TMS-project`.

## 3. Restore the database
Open PowerShell. Use your own MySQL root password and your MySQL install path (find it with `Get-ChildItem "C:\Program Files\MySQL"`).

```powershell
$mysql = 'C:\Program Files\MySQL\MySQL Server 9.5\bin\mysql.exe'   # adjust the version folder
$env:MYSQL_PWD = '<your MySQL root password>'

# 3a. app user (the password must match the one inside backend\.env, see step 4)
& $mysql -uroot -e "CREATE USER IF NOT EXISTS 'tms_user'@'localhost' IDENTIFIED BY 'mLgoFOlysO8iiGeB4GrHi1Oc';"

# 3b. import the dump (it creates the database `tms`)
cmd /c "`"$mysql`" -uroot < D:\TMS\TMS-project\tms_db_dump.sql"

# 3c. permissions, plus an empty database for the automated tests
& $mysql -uroot -e "CREATE DATABASE IF NOT EXISTS tms_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL ON tms.* TO 'tms_user'@'localhost'; GRANT ALL ON tms_test.* TO 'tms_user'@'localhost';"

# 3d. check: should print 48 (tables) and the number of users
& $mysql -uroot -e "SELECT COUNT(*) AS tables_in_tms FROM information_schema.tables WHERE table_schema='tms'; SELECT COUNT(*) AS users FROM tms.users;"
Remove-Item Env:MYSQL_PWD
```

The `tms_user` password above is the one currently in `backend\.env`. If you prefer a different password, change it in both places (the `CREATE USER` line and the two URLs in `.env`).

## 4. Check `backend\.env`
Open `D:\TMS\TMS-project\backend\.env`. It already works if you used the password above. Things to know:
- `TMS_DATABASE_URL` / `TMS_TEST_DATABASE_URL`: user, password, host `localhost`, port `3306`. Change the port if your MySQL does not use 3306.
- `TMS_EMAIL_BACKEND=smtp` sends **real email** through the company mailbox. For testing without sending mail set `TMS_EMAIL_BACKEND=log`. Emails to `@demo.example.com` addresses are skipped automatically anyway.
- `TMS_DEV_MULTI_SESSION=true` lets you stay signed in as several roles in different browser tabs. Dev only.
- `TMS_INLINE_JOBS=true` runs reminders, notifications and email inside the API process. No Redis or Docker is needed.

## 5. Install and start the backend
```powershell
cd D:\TMS\TMS-project\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head      # does nothing if the dump is already current (expected)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```
Leave this window open. Check http://localhost:8000/healthz shows `{"status":"ok"}`. API docs: http://localhost:8000/docs.

## 6. Install and start the frontend (second PowerShell window)
```powershell
cd D:\TMS\TMS-project\frontend
npm install
npm run dev
```
Open **http://localhost:5173**.

## 7. Sign in
Password for every demo account: `Demo@12345!`

| Role | Email |
|---|---|
| Admin | admin@demo.example.com |
| Owner | owner@demo.example.com |
| CEO | ceo@demo.example.com |
| Manager | manager@demo.example.com |
| Department Heads | devhead@ , hrhead@ , mktghead@demo.example.com |
| Employees | abc@ , frontend@ , hr1@ , marketing1@ , support1@ , sales1@ , accounts1@demo.example.com |

If people changed their passwords or were added after the demo seed, those changes are in the dump too.

## 8. Optional: verify everything with the tests
```powershell
cd D:\TMS\TMS-project\backend
.\.venv\Scripts\python.exe -m pytest        # about 8 minutes, expects 1116 passed, uses the tms_test database
.\.venv\Scripts\python.exe -m ruff check app tests
cd ..\frontend
npm run typecheck
npm run build
```
Never point `TMS_TEST_DATABASE_URL` at `tms`: the tests wipe their database.

## 9. If you would rather start from a clean database instead of the dump
Skip step 3b, then run (inside `backend`): `alembic upgrade head`, then `.\.venv\Scripts\python.exe -m app.cli seed-demo`.

## Troubleshooting
| Problem | Fix |
|---|---|
| `Access denied for user 'tms_user'` | The password in `.env` does not match MySQL. Re-run the `CREATE USER` and `GRANT` lines, or `ALTER USER 'tms_user'@'localhost' IDENTIFIED BY '<password from .env>';` |
| `Can't connect to MySQL server` | Start the service: `Start-Service MySQL95` (use your service name) in an administrator PowerShell, and check the port in `.env`. |
| Import says `Unknown collation` | Your MySQL is older than 8.0. Install MySQL 8 or newer. |
| Login page loads but sign-in fails | Check the API window for errors, and that `TMS_CORS_ORIGINS` is `http://localhost:5173`. |
| Port 8000 or 5173 busy | Close the other program, or change the port (and update `TMS_CORS_ORIGINS` and the proxy in `frontend/vite.config.ts`). |
| `pip install` fails on Python 3.14 | Use Python 3.12 or 3.13. |
| Emails fail | Set `TMS_EMAIL_BACKEND=log` while testing. |

## More documents
`SETUP.md` (short setup and a 5-minute walkthrough), `docs/12-user-guides.md` (how each role uses the system), `docs/13-security-checklist.md`, `docs/progress.md` (what is built), `docs/03-roles-permissions.md` (who can do what).

## Before you hand this zip to anyone else
Rotate the secrets in `backend/.env`: the `tms_user` password, `TMS_SECRET_KEY` and the SMTP password. Delete the zip from shared locations when you are done.
