# TMS on cPanel shared hosting (Passenger + cron)

How it runs: the API is a Python app served by Passenger (`passenger_wsgi.py`, FastAPI converted to WSGI by `a2wsgi`).
Nothing runs permanently: no Uvicorn, no systemd, no Redis, no Celery, no WebSocket. Reminders, notifications and email
are processed by a **cPanel cron job every minute**. The browser learns about new notifications by polling
`GET /api/v1/notifications/unread-count` every 20 seconds.

Placeholders used below: `USERNAME` = your cPanel user, `APPDIR` = the application folder you choose (example: `tms`),
`DOMAIN` = `tksb.pro.seawindsolution.com`.

---

## 1. Python 3.12 application
cPanel -> **Software -> Setup Python App** -> *Create Application*

| Field | Value |
|---|---|
| Python version | **3.12** |
| Application root | `APPDIR` (becomes `/home/USERNAME/APPDIR`) |
| Application URL | `DOMAIN` (the whole domain, no sub-path) |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

Upload `backend.zip` with **File Manager** to `/home/USERNAME/APPDIR` and extract it there, so that
`/home/USERNAME/APPDIR/passenger_wsgi.py` and `/home/USERNAME/APPDIR/app/` exist. If 3.12 is not in the list, ask the host to enable it.

## 2. Virtual environment
Creating the app in step 1 creates the virtualenv at `/home/USERNAME/virtualenv/APPDIR/3.12/`. Open it in a terminal
(the Python App page shows the exact `source .../bin/activate` line you can copy):

```bash
source /home/USERNAME/virtualenv/APPDIR/3.12/bin/activate
cd /home/USERNAME/APPDIR
```

## 3. Requirements
```bash
pip install --upgrade pip
pip install -r requirements.txt        # includes a2wsgi; no uvicorn / websockets
```
(The Python App page also has an *Add requirements file* button: `requirements.txt` then *Run Pip Install*.)

## 4. `.env`
Edit `/home/USERNAME/APPDIR/.env` (File Manager -> *Show hidden files*). The one in the zip is production-ready except the
database line.

```ini
TMS_ENV=production
TMS_DATABASE_URL=mysql+pymysql://CPUSER_tms:DB_PASSWORD@localhost:3306/CPUSER_tms?charset=utf8mb4
TMS_SECRET_KEY=<64 random characters>
TMS_APP_BASE_URL=https://tksb.pro.seawindsolution.com
TMS_CORS_ORIGINS=https://tksb.pro.seawindsolution.com
TMS_COOKIE_SECURE=true
TMS_DEV_MULTI_SESSION=false
TMS_INLINE_JOBS=false
TMS_FRONTEND_DIR=/home/USERNAME/public_html      # the folder where the website (index.html) is unzipped, see step 11
TMS_EMAIL_BACKEND=smtp   # + TMS_SMTP_HOST / PORT / SECURITY / USER / PASSWORD / EMAIL_FROM (already filled in)
```
* Create the database and user in **cPanel -> MySQL Databases** (names get your `CPUSER_` prefix; give the user *All Privileges*).
* If the password contains `@ : / # ?` it must be URL-encoded in `TMS_DATABASE_URL` (`@` -> `%40`).
* The HTTPS certificate must be active (AutoSSL) because cookies are `Secure`.
* `TMS_INLINE_JOBS` is ignored (the API never starts jobs); it is there so nobody wonders.

## 5. `passenger_wsgi.py` (already in the zip, do not edit)
```python
import os, sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR); os.chdir(BASE_DIR)
from a2wsgi import ASGIMiddleware
from app.main import app
application = ASGIMiddleware(app)
```

## 6. Database
Two ways; use the first (it keeps the current accounts, roles and notification rules):

**A. Import the SQL file** (`tms_db_dump.sql`, plain SQL, MySQL 5.7+ / 8): cPanel -> *phpMyAdmin* -> select your **empty** database ->
*Import* -> choose `tms_db_dump.sql` -> *Go*. (Or: `mysql -u CPUSER_tms -p CPUSER_tms < tms_db_dump.sql`.) The file has no
`CREATE DATABASE` line, so it loads into whatever database you selected, and its collation is `utf8mb4_unicode_ci`, which every
MySQL version accepts. It is already at the latest schema; running `alembic upgrade head` afterwards changes nothing.

**Upgrading an existing database** (instead of importing the dump): `python -m alembic upgrade head` then `python -m app.cli seed-core` (adds the QA/loop notification rules; it never overwrites Admin edits).

**B. Start empty** (no old data): `python -m alembic upgrade head` then `python -m app.cli bootstrap-admin --email you@company.com`.

Either way, check the connection and the server version:
```bash
python app/jobs/run_once.py --check        # prints: database server version: 5.7.x / 8.x
```
The app no longer uses `SKIP LOCKED` (the cause of the "SQL syntax error near SKIP LOCKED" on older MySQL).

## 7. Cron job (the scheduler)
cPanel -> **Advanced -> Cron Jobs** -> *Add New Cron Job*: *Once Per Minute (`* * * * *`)*, command (one line, replace the names):

```
/home/USERNAME/virtualenv/APPDIR/3.12/bin/python /home/USERNAME/APPDIR/app/jobs/run_once.py >> /home/USERNAME/APPDIR/logs/cron.log 2>&1
```
* One run = reminder scan, events -> notifications, send emails and retries. It exits when done.
* If a run is still working when the next minute starts, the new run sees the database lock, exits immediately and does nothing:
  jobs are never processed twice. A run that is killed frees its lock automatically (the lock lives on its database connection).
* Optional, faster email (a pass every 10 s instead of once a minute): add `--duration 50 --interval 10` after `run_once.py`.
* Log files: `logs/scheduler.log` (rotating, 2 MB x 3, written by the script) and `logs/cron.log` (whatever the cron shell prints).

## 8. Restart the application
After changing `.env`, code or requirements: **Setup Python App -> your app -> Restart**, or
```bash
mkdir -p /home/USERNAME/APPDIR/tmp && touch /home/USERNAME/APPDIR/tmp/restart.txt
```
The cron job needs no restart: it starts fresh every minute.

## 9. Test the API
```bash
curl -i https://DOMAIN/healthz                       # 200 {"status":"ok"}
curl -i https://DOMAIN/api/v1/auth/me                # 401 = the API is reachable and asks for login
```
Open `https://DOMAIN/docs` (Swagger). Sign in on the website, open the bell: the number updates within 20 s without a refresh.

## 10. Test the scheduler
```bash
/home/USERNAME/virtualenv/APPDIR/3.12/bin/python /home/USERNAME/APPDIR/app/jobs/run_once.py ; echo "exit=$?"
```
Expect `database server version ...`, `pass 1 done: {...}` and `exit=0`. In the website: **Administration -> Notifications & Jobs**
shows *Scheduler (cron): Running* (a pass in the last 3 minutes), the queued/failed email counts, and *Run a pass now*.
Email test: `python -m app.cli send-test-email --to you@company.com`.

Admin routes (all need an Admin login; there is **no public scheduler URL**):

| Method | Route | Use |
|---|---|---|
| GET | `/api/v1/admin/jobs/status` | last pass time, whether cron is running, queue sizes |
| GET | `/api/v1/admin/jobs/failures` | the last 100 job failures |
| POST | `/api/v1/admin/jobs/run-now` | run one pass now (same lock as cron; `409 SCHEDULER_BUSY` if cron is mid-run) |

## 11. The website (frontend)
Unzip `frontend-build.zip` into the domain's document root (`/home/USERNAME/public_html`, or the folder cPanel shows for
the domain). Do not delete the `.htaccess` that cPanel/Passenger created there. Files in that folder are served by Apache;
every other address (`/api/...`, `/docs`, and page URLs like `/tasks/5` through `TMS_FRONTEND_DIR`) goes to the app.

## 12. Log files and troubleshooting
| Where | What |
|---|---|
| `/home/USERNAME/APPDIR/logs/scheduler.log` | every cron pass and its errors |
| `/home/USERNAME/APPDIR/logs/cron.log` | cron stdout/stderr (import errors, wrong paths) |
| `/home/USERNAME/logs/` or the Python App page -> *stderr.log* | Passenger / API errors |
| Admin -> Notifications & Jobs -> failures / Email log | job failures and every email with its error |

| Symptom | Cause / fix |
|---|---|
| Passenger "Incomplete response" / 500 on every page | Wrong startup file/entry point (must be `passenger_wsgi.py` / `application`), missing `pip install`, or a bad `.env` (read stderr.log). Restart after fixing. |
| `ModuleNotFoundError: app` in cron | Use the full path to `app/jobs/run_once.py` (the script finds the project itself). |
| `ModuleNotFoundError: a2wsgi` / other | Requirements not installed into **this** virtualenv: activate it (step 2) and repeat step 3. |
| `You have an error in your SQL syntax ... SKIP LOCKED` | Old code. This version never sends `SKIP LOCKED`: re-upload `backend.zip`. |
| `Access denied for user` / `Unknown database` | Wrong `TMS_DATABASE_URL`: use the `CPUSER_` prefixed names and URL-encode the password. |
| `Unknown collation: utf8mb4_0900_ai_ci` | An old MySQL-8 export was imported. Use the `tms_db_dump.sql` from this package (collation already converted). |
| Admin shows *Scheduler (cron): Stopped / Never ran* | Cron not saved, wrong python path, or errors in `cron.log`; run step 10 by hand. |
| Emails stay *queued* | Cron not running, or outside working hours (routine mail waits; invitations/assignments go at once). Check the Email log error. |
| Emails link to `localhost` | `TMS_APP_BASE_URL` not set; restart the app. |
| Login works, then logs out immediately | Site not on HTTPS while `TMS_COOKIE_SECURE=true`. |
| Refreshing `/tasks/5` shows a JSON 404 | `TMS_FRONTEND_DIR` not set, or `index.html` is not in that folder. |
| Notification number does not change | Cron not running (no new notifications are created) or the browser tab is hidden (polling pauses). |
| `409 SCHEDULER_BUSY` on *Run a pass now* | Cron is mid-run; try again in a few seconds. |

Uploaded attachments are stored in `APPDIR/uploads/`: keep it and back it up with the database.


## Where the website and the API live (two addresses)
If the website is on one address (e.g. `https://tksf.pro.seawindsolution.com`) and the API on another
(`https://tksb.pro.seawindsolution.com`):
- Website folder: upload `frontend-build.zip` contents, and edit `config.js` there: `apiBase: "https://tksb.pro.seawindsolution.com"`.
  (If login shows "Unexpected token '<' ... is not valid JSON" or "Cannot reach the API server", the website is calling itself: fix `apiBase`.)
- API `.env`: `TMS_CORS_ORIGINS=https://tksf.pro.seawindsolution.com` (the website address, comma-separated for several),
  `TMS_APP_BASE_URL=https://tksf.pro.seawindsolution.com` (links in emails), `TMS_COOKIE_SECURE=true`.
- Email: `TMS_MAIL_AFTER_REQUEST=true` sends mail right after each change (ADR 007). Still add the cron job (section 7): reminders
  and retries need it. Check `python -m app.cli send-test-email --to you@company.com` and Admin -> email log for SMTP errors.
