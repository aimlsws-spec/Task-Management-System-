# ADR 008: Emailed one-time code at sign-in, random employee IDs, department head and QA in the review chain

Status: accepted. Requirements: sign-in security (NFR security), FR on review chain (ADR 003, 006).

## 1. One-time code (OTP) on every sign-in and sign-up
- Sign-in is two steps. `POST /auth/login` checks email + password (lockout rules unchanged). When `TMS_OTP_ENABLED=true` (default)
  it returns `{otp_required, challenge, email_hint, expires_in, resend_after}` and **no session**; a 6-digit code is emailed to the
  address registered on the account. `POST /auth/verify-otp {challenge, code}` returns the usual tokens. `POST /auth/resend-otp`
  mails a fresh code.
- Applies to everybody: Admin, Owner, CEO, Manager, Department Head, Employee. Sign-up (`POST /auth/signup`) creates the account and
  returns the same challenge, so the mailbox is proven before the first session.
- Safety: only SHA-256 hashes are stored (`login_otps`; the code is hashed with the challenge and the secret key). 10 minutes
  validity, 5 wrong tries kill the challenge, a new sign-in voids older challenges, resend waits 30 s and is limited to 5, per-IP
  rate limits, every step is audited. Wrong password never sends a code and gives the same generic message as before.
- The code email is sent **directly from the request** (not through the email queue): it must not wait for cron and must not sit in
  the email log. If the mail server fails the person sees "We could not send the code" (HTTP 503) and gets no session.
- Emergency switch: `TMS_OTP_ENABLED=false` returns to password-only sign-in (use only if mail is down and nobody can get in).
- Tests run with the switch off (`tests/conftest.py`); `tests/test_otp.py` turns it on.

## 2. Employee IDs
- Generated IDs are random and always contain letters and digits: `SW-` + 6 characters (no I, O, 0, 1), e.g. `SW-7K2QX9`.
  Sign-up and the Admin "add employee" form generate one; the Admin may type a custom ID only if it is 4-30 characters of letters,
  digits and dashes with at least one letter and one digit, is not a simple counter (`EMP-001`, `ID7`...), and is unique
  (case-insensitive, stored upper-case). Migration 0012 replaces existing `EMP-nnnn` codes.

## 3. Who reviews finished work
Every task finished by an employee is reviewed; only work done by the Owner or CEO themselves is completed directly.
Chain: **QA -> head -> CEO/Owner -> Completed**. A stage is skipped when nobody is set, when the person is the assignee, or when the
same person was already asked.
- **Head** = the task's head, else the project's head, else the **head of the assignee's department**.
- **QA** = the task's QA, else the project's QA, else the department's **QA tester** (new `departments.qa_employee_id`, set by the
  Admin on the Departments page, `PUT /departments/{id}/qa`). Typically only the development department has one.
- With no head and no QA anywhere (e.g. Sales/Marketing department without a head) the task goes straight to the CEO/Owner.
- The department head and QA are also "in the loop": they are notified and mailed about the task, its comments and blockers.

## Consequences
- Old behaviour "a task with no head, QA or project completes directly" is gone; tests were updated for the new rule.
- After upgrading an existing database run `alembic upgrade head`; existing departments have no QA tester until the Admin picks one.

## 4. Hosting layout (final): two addresses
Website `https://tksf.pro.seawindsolution.com` (static files, `frontend-build.zip`, with `.htaccess` so page addresses work on refresh) and API
`https://tksb.pro.seawindsolution.com`. The API allows the website's origin (`TMS_CORS_ORIGINS`), and `TMS_APP_BASE_URL` (links in emails) is the website.
The two are sub-domains of one site, so the SameSite refresh cookie works. `app/core/dbguard.py` answers 503 `DB_OUTDATED` when the database is behind
the code and returns JSON 500s that still carry CORS headers (a browser otherwise only shows "Failed to fetch"). `upgrade_0011_to_0012.sql` upgrades a kept database.

## 5. The database upgrades itself (`TMS_AUTO_MIGRATE`, default true)
The first /api request after a deployment compares `alembic_version` with the code's head. If behind, it runs `alembic upgrade head` once under a MySQL
named lock (`tms_migrate`), so several Passenger workers never migrate at once. Migrations in this project are additive. If it cannot (privileges, ...) the API answers
503 `DB_OUTDATED` with the reason. This removes the "new code, old database" 500 for good: replace files, Restart, done.
