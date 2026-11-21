# ADR 002: Role emails registered by the Admin; no audit log for Owner and CEO; no demo data

**Status:** accepted (2026-11-17). Changes the matrix in doc 03 (Owner and CEO lose `audit.view`).

## Context
The system started with a sample organization (Owner, CEO, heads, employees) and let Owner and CEO read the audit log.
The product owner decided that the real company will sign up fresh, that the Admin builds the organization in the Admin
panel, and that Owner and CEO do not need the audit log.

## Decisions
1. **Audit log is Admin-only.** `audit.view` is removed from Owner and CEO (RBAC seed version 4). Existing databases get the
   new defaults the next time the API seeds the roles. Owner and CEO keep every work permission.
2. **Role emails.** The Admin registers an email with a role (Owner, CEO, Manager, Department Head or Employee; never Admin) on
   *Administration > Role emails* (`/role-invites`, permission `employee.manage`). When someone signs up with exactly that
   email (case-insensitive) they receive that role at once. Owner, CEO and Manager skip onboarding and join *Management*;
   the CEO reports to the Owner and the Manager to the CEO (else the Owner). Anyone not registered is a plain Employee, as before.
   If the person already has an account, the role is added immediately and their sessions end so they sign in again.
   Each email is claimed once; an unclaimed one can be removed; every step is audited.
3. **Department heads are set by the Admin.** Naming a head on *Departments* also gives that person the Department Head role (never
   downgrading a Manager/CEO/Owner). The person replaced loses the role unless they still head another department, and
   falls back to Employee. Both are signed out so the change applies at the next login.
4. **No demo data in the product.** The seed creates only the two system departments (Management, Unassigned), the roles and the
   rules. The first account is created with `python -m app.cli bootstrap-admin`; the Admin creates departments and everything else.
   The sample organization lives only in `backend/tests/demo_org.py` as a test fixture.

## Risk accepted (please read)
Sign-up does not verify email ownership. Anyone who knows a registered Owner/CEO email and signs up with it *before the real
person does* receives that role. Mitigations today: the Admin sees "Signed up / Waiting" per email, can only register an email
shortly before the person signs up, and every claim is in the audit log. **Before this is used on the open internet, add email
verification** (a one-time link, using the existing email outbox) and grant the role only after it is clicked.

## Addendum (2026-11-17): emails, fixed timezone, menu
- Registering a role email **sends that address an invitation** (sign-up link; or "sign in again" if they already have an account).
- A new sign-up raises `EMPLOYEE_SIGNED_UP`: every Owner gets an in-app notification and an email (an Admin-editable rule).
- Emails people act on are **never held for working hours**: task assigned/reassigned, 24 h and 2 h reminders, overdue and escalations,
  delay reasons and their review, extension decisions, new sign-ups, invitations. Other routine mail still waits for 09:30-18:30.
- Real delivery needs SMTP in `backend/.env` (`TMS_EMAIL_BACKEND=smtp`, `TMS_SMTP_*`, `TMS_EMAIL_FROM`); until then mail is only written to the log.
- The **Settings screen was removed**: the company timezone is fixed (Asia/Kolkata) and End-of-day is 18:30. The API endpoint remains but nothing in the UI changes it.
- *Audit log* is the last tab of the Administration menu.
