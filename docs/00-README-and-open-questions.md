# Task Management System — Planning Pack (v0.1, for review)

Status: **PLANNING ONLY. No code has been written.** Approval of this pack is the gate to Phase 2.
Date: 2026-11-16 · Project dir was empty (greenfield). Dev machine: Python 3.14.4, Node 24, MySQL 8.0.46, Docker 29, Redis 3.0.504 (too old → run Redis 7 in Docker).

## Documents

| # | File | Contents |
|---|---|---|
| 1 | [01-BRD.md](01-BRD.md) | Business objective, users, hierarchy, workflows |
| 2 | [02-SRS.md](02-SRS.md) | FR / NFR with IDs, status machine, rules |
| 3 | [03-roles-permissions.md](03-roles-permissions.md) | Access-control model + role × permission matrix |
| 4 | [04-architecture.md](04-architecture.md) | Frontend, backend, auth, notifications, jobs, deployment (Mermaid) |
| 5 | [05-database.md](05-database.md) | ER diagram, every table, constraints, indexes |
| 6 | [06-api.md](06-api.md) | Endpoint catalogue |
| 7 | [07-ui-ux.md](07-ui-ux.md) | Screens, navigation per role, layouts |

| 9 | [09-business-rules-edge-cases.md](09-business-rules-edge-cases.md) | 16 edge cases + recommended behaviour |
| 10 | [10-final-recommendation.md](10-final-recommendation.md) | Stack, MVP, risks, future |

## Headline decisions (details in the documents)

1. **Access control = RBAC + scope**, not three separate systems. Roles carry *permissions*; each permission is granted with a *scope* (`self | team | department | organization`). "Team" is resolved from the **reporting_relationships** table; "department" from **departments**. Owner/CEO = organization scope. Nothing is hardcoded to the names Owner/CEO/Manager — they are seed data.
2. **"Overdue" is not a status.** It is derived (`due_at < now` and task not finished). A task can be *In Progress and overdue*. This fixes the status list you proposed (see SRS §3).
3. **"Pending" is dropped** from the stored statuses (ambiguous with Assigned/Acknowledged/On Hold); it remains as a dashboard grouping.
4. **One active timer per employee** (DB-enforced), but many open tasks. Blocked time is excluded from active time.
5. **Deadlines are append-only** (`task_deadline_history`); `tasks.original_due_at` is immutable.
6. **Reminders are scanned, not pre-scheduled**: a per-minute job finds due reminders and de-duplicates with a unique key containing the deadline version → stale reminders are impossible after an extension/completion.
7. **Notifications** are driven by an `outbox_events` table + a **recipient-resolution engine** driven by rules in the database (`notification_rules`) → no hardcoded recipients.
8. **Modular monolith**: FastAPI + MySQL + Redis/Celery + React. No microservices.
9. **Completion = employee self-assurance; review is optional (decided, latest answer).** The assignee marks the task Completed after confirming an assurance checklist (what was done, tested yes/no, notes). Manager/Dept Head/CEO/Owner may *verify* it, or **revert** it (→ Reopened, with reason code such as "QA defect") whenever QA or review finds the feature not working. Review can be made compulsory per task type/project. *(Supersedes the earlier "employees cannot complete" answer — please confirm.)*
11. **Work calendar is first-class**: shifts 09:30–13:30 and 14:00–18:30 (30-min break 13:30–14:00 = **8.5 productive h/day**), Mon–Sat working except **2nd and 4th Saturday**, **every Sunday off**, plus a holidays table. Capacity, EOD, reminders and escalations all use it.
14. **Admin role + Admin panel (decided).** Employees, departments (add/edit/delete, heads), hierarchy, roles & permissions and settings are managed only by an **Admin**, never in Owner/CEO/Manager panels. Owner/CEO keep full task authority. New employees self-register with a company email, then choose department + designation at first login and are grouped under that department's head (or the Manager when there is none). Sign-up accepts any email address (the domain restriction was removed by decision); it is rate-limited, has no email verification until Phase 6, and a new account sees nothing until it is onboarded and placed.
13. **MySQL 8 is the only database (decided).** No SQLite/Postgres/NoSQL anywhere — not in dev, not in tests. The code refuses any non-MySQL URL; tests run on a dedicated `*_test` MySQL database whose schema is built by the Alembic migrations.
12. **Hosting/deployment is out of scope for now.** Dev environment only (Docker Compose for local MySQL-adjacent services). A later "Hosting & go-live" phase is left unplanned.
10. Pin **Python 3.12 or 3.13** for production, not 3.14 (library wheels / Celery ecosystem lag on brand-new interpreters). Decision to confirm in Phase 1.

## Questions Requiring Business Confirmation (each has a recommended default)

I have **not** silently assumed any of these; the default is what the plan is built on if you don't answer.

| # | Question | Recommended default |
|---|---|---|
| Q1 | ✅ **ANSWERED: one Manager.** | Single Manager above all departments; the model still supports more later (no schema change). Manager scope = whole reporting subtree. |
| Q2 | ✅ **ANSWERED: no upward assignment.** | Assign only to equal-or-lower rank within scope (rank check enforced server-side). |
| Q3 | ✅ **ANSWERED: employees do not create tasks.** | Removed entirely (no feature flag). Employees only act on tasks assigned to them. |
| Q4 | ✅ **ANSWERED (revised): employee marks Completed with an assurance; review optional; Manager can revert.** | Employee: *Mark Complete* (guards: assurance checklist, no open blocking blocker, time logged or justification). Manager/Head/CEO/Owner: optional *Verify*, or *Revert* → Reopened with reason code (qa_defect, incomplete, requirement_change, other) + note. `requires_review` default **off**, configurable per task type/project (when on, employee uses *Submit for review* instead). Revert counts are reported as rework, not as a score. |
| Q5 | Who may verify/revert? *(answered in substance)* | Manager, Dept Head (own dept), CEO, Owner. Assigner may also verify tasks they assigned. |
| Q6 | ✅ **ANSWERED: date-only = EOD in company timezone; exact time also allowed.** Company hours are 09:30–18:30 | EOD = **18:30** company time (setting `eod_time`). Form: date + "EOD" toggle (default) or exact time. **Company timezone value still needed** (setting). |
| Q7 | ✅ **ANSWERED: 09:30–18:30; 2nd & 4th Saturdays off, other Saturdays working.** | Work calendar = weekly pattern + "nth weekday off" rules + holidays table. **Confirmed:** every Sunday off; 2nd & 4th Saturday off; other Saturdays working; shifts 09:30–13:30 and 14:00–18:30. "Overdue" stays wall-clock (a deadline is a point in time); pre-deadline reminders are wall-clock; **post-deadline escalations (+1d/+3d/+7d) count working days**; non-urgent emails are sent inside working hours. Deadlines set on a non-working day trigger a warning. |
| Q8 | Daily capacity per employee for workload? | ✅ **ANSWERED:** 09:30–13:30 + 14:00–18:30 → **8.5 productive h/working day** (30-min break), per-employee override; capacity = Σ working days (calendar-aware) in the next 7 days. Thresholds: ≤80% Normal, 80–100% High, >100% Overloaded. |
| Q9 | ✅ **DESIGNED (your delegation).** Forgotten timers | Check-ins at 4h/8h and at 19:00; hard cap 10h or 22:00 company time; auto-closed time is provisional until confirmed. Full rule in [02-SRS.md §6](02-SRS.md). |
| Q10 | May employees manually add time ("I forgot the timer")? | Yes, as *pending correction* needing manager approval; never silently applied. |
| Q11 | Is Owner a user who also uses the system as an employee (gets tasks)? | Owner/CEO can be assignees only if flagged; default no. |
| Q12 | Employee exits: reassign automatically? | No auto-reassign; tasks flagged "orphaned" to manager's queue (see doc 9). |
| Q13 | Delay-reason rule: required once per overdue episode, or repeatedly? | Required once after overdue; **re-required** after each approved extension that is missed again, and after 3 days of no update. |
| Q14 | Reminder intervals (24h, 2h, due, +1d, +3d, +7d) and escalation targets | As specified; escalation chain: +3d → Manager + CEO, +7d → Manager + CEO + Owner. Configurable. |
| Q15 | Email provider / SMTP, sender domain, expected volume | Any SMTP; SPF/DKIM required; assume < 500 emails/day. |
| Q16 | Number of users, concurrent users, data retention | Assume ≤ 200 users, ≤ 100 concurrent; keep all history 7 years, attachments 3 years. |
| Q17 | File attachment limits and types | 25 MB/file, allow-list (pdf, docx, xlsx, png, jpg, zip, txt, csv), AV-scan hook; stored on disk/S3-compatible. |
| Q18 | Productivity "scores"? | None. Report 4 separate measures (completion, on-time rate, active hours, elapsed). |
| Q19 | Multi-assignee tasks? | Single accountable assignee in MVP; group work = sub-tasks. |
| Q20 | Monitoring intensity (screenshots, idle detection)? | **Out of scope.** Timer is self-reported start/stop only. Needs a legal/HR decision before ever adding. |
| Q21 | Single company or multi-tenant SaaS? | Single company; keep a nullable `organization_id`-free design (no tenancy now). |
| Q22 | Languages / RTL / SSO (Google/Microsoft)? | English only; SSO deferred (auth module is pluggable). |
| Q23 | MFA required for Owner/CEO? | Recommended yes (TOTP) — Phase 2 stretch / Phase 9 hardening. |
| Q24 | ✅ **ANSWERED: do not plan hosting now.** | Deployment, Nginx/TLS, backups, monitoring and go-live are removed from the roadmap (deferred, see [04-architecture.md §8](04-architecture.md)). Build targets local dev + CI only. |

## How the project will be built "with Claude"

See [08-roadmap.md §B](08-roadmap.md). Summary: spec-in-repo + `CLAUDE.md`, one phase = one branch/PR series, Plan → implement → test → `/code-review` + `/security-review` → human approval gate. Permission matrix is turned into an automated test table so Claude cannot silently weaken authorization.
