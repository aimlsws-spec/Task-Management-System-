# SeaWind Task Management: deployment quickstart (ONE address)

Everything (website and API) runs at `https://tksb.pro.seawindsolution.com`.
Files: `backend.zip` (the API **and** the website, with `.env`), `tms_db_dump.sql` (database with only the Admin account).
`frontend-build.zip` is the same website on its own: use it only if you host the website somewhere else.

## 1. Database (cPanel -> MySQL Databases)
Create a database and a user, give the user ALL privileges. phpMyAdmin -> select that EMPTY database -> Import -> `tms_db_dump.sql`.

## 2. The app (cPanel -> Setup Python App)
| Field | Value |
|---|---|
| Python version | 3.12 |
| Application URL | `tksb.pro.seawindsolution.com` (the whole domain, no sub-path) |
| Startup file / entry point | `passenger_wsgi.py` / `application` |

1. Extract `backend.zip` into the application folder (you must see `passenger_wsgi.py`, `app/`, `frontend/`, `.env` there).
2. Edit `.env` and set ONLY this line (everything else is ready):
   `TMS_DATABASE_URL=mysql+pymysql://DBUSER:DBPASSWORD@localhost:3306/DBNAME?charset=utf8mb4`
   (If you forget, the app says: "Edit TMS_DATABASE_URL in .env".)
3. In the app's terminal: `pip install -r requirements.txt`, then press Restart.
4. Open `https://tksb.pro.seawindsolution.com/healthz` -> must show `{"status":"ok"}`.
5. Open `https://tksb.pro.seawindsolution.com/login` (Ctrl+F5) and sign in with the Admin account.
6. Cron job, every minute (needed for deadline reminders and mail retries):
   `/home/USER/virtualenv/APPDIR/3.12/bin/python /home/USER/APPDIR/app/jobs/run_once.py >> /home/USER/APPDIR/logs/cron.log 2>&1`

## How to be sure the NEW website is running
- Sign-in page, bottom left, small text: `Build 2026-... UTC · API tksb.pro.seawindsolution.com`.
- DevTools -> Network: the login request goes to `https://tksb.pro.seawindsolution.com/api/v1/auth/login` and the script is `assets/index-DqYhpq6K.js`.
- `https://tksb.pro.seawindsolution.com/config.js` opens and shows `apiBase: "https://tksb.pro.seawindsolution.com"`.
If any of these is not true, old files are being served: delete the old app files, extract again, Restart, Ctrl+F5.

## If something shows an error
| Message | Meaning / fix |
|---|---|
| `Unexpected token '<' ... is not valid JSON` / `Cannot reach the API server` | The browser is calling a wrong address or an old build. Check the three points above. |
| `Failed to fetch` + CORS message in the console | Only when the website is opened from another address: put that address in `TMS_CORS_ORIGINS` in `.env`, Restart. |
| `healthz` fails / 500 | `TMS_DATABASE_URL` wrong, or `pip install` not done. See `logs/` and the Python App page. |
| No emails | In the app terminal: `python -m app.cli send-test-email --to you@company.com`; Admin -> email log shows SMTP errors. |
