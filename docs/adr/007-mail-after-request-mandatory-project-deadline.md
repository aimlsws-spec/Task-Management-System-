# ADR 007: mail processed right after a change, mandatory project deadline, project deadline reminders, runtime API address

Status: accepted. Deviates from ADR 001/005 ("jobs run ONLY from cron") in one narrow way.

1. **Mail after each change.** With `TMS_MAIL_AFTER_REQUEST=true`, after a successful POST/PUT/PATCH/DELETE under `/api/v1`
   (not auth, not notifications) the API runs ONE scheduler pass (`jobs/kick.py` -> `run_locked`) as a Starlette background task,
   after the response was sent. No thread or process is started; it takes the same named lock as cron, so passes never overlap.
   Reason: deployments where the cron job was not (yet) configured produced no email at all. Cron remains the safety net and the
   only guarantee for reminders when nobody uses the site. Default off (tests, dev); on in the shipped production `.env`.
2. **A project deadline (`ends_on`) is mandatory**, not in the past, not before `starts_on`, and cannot be removed.
3. **Project deadline reminders** (scheduler tick): the day before, the day of, and once overdue (up to 7 days late), to the
   head, QA, team and creator; overdue also to CEO and Owner. Once each (dedupe key).
4. **Mail for projects:** everyone added (head, QA, member) gets an email with the deadline and expected result; CEO and Owner are
   emailed when a project is created. New tasks mail the whole loop. All these go out immediately.
5. **The API address is a runtime setting** (`/config.js` next to `index.html`), falling back to the build-time
   `VITE_API_BASE_URL`, so a deployer can fix it without a rebuild; a non-JSON answer shows "Cannot reach the API server".

6. **One address.** If a `frontend/` folder (the built website) sits next to `app/`, the API app serves it too (real files as they are, every
   other page URL -> `index.html`), so `backend.zip` alone gives website + API on `https://tksb.pro.seawindsolution.com`. No `.htaccess` is
   shipped (cPanel writes its own Passenger block there). `TMS_FRONTEND_DIR` can point elsewhere.
