# Document 2 — Software Requirement Specification (SRS)

Priority: **M** = MVP, **S** = Should (post-MVP v1), **C** = Could.

## 1. Roles (seed; fully editable)
Owner, CEO, Manager, Department Head, Employee, plus `Admin` capability (granted to Owner by default). See [doc 3](03-roles-permissions.md).

## 2. Functional requirements

### Authentication & accounts
| ID | Requirement | P |
|---|---|---|
| FR-001 | Email+password login; generic errors; lockout after N failures (default 5/15 min) | M |
| FR-002 | JWT access token (15 min) + rotating refresh token (httpOnly cookie, reuse detection) | M |
| FR-003 | Logout (revoke refresh family), logout-all-devices | M |
| FR-004 | Forgot/reset password via single-use, 30-min tokens | M |
| FR-005 | Force password change on first login; password policy | M |
| FR-006 | TOTP MFA (mandatory for Owner/CEO) | S |
| FR-007 | User profile: name, phone, timezone, notification preferences | M |

### Organization
| ID | Requirement | P |
|---|---|---|
| FR-010 | CRUD departments (name, optional head, optional parent); deactivate, never hard-delete | M |
| FR-011 | CRUD employees (profile, department, job title, status active/inactive/on-leave, daily capacity) | M |
| FR-012 | Reporting relationships: employee → reporting person, effective-dated, no cycles, one *primary* manager at a time | M |
| FR-013 | Dynamic roles & permissions (permission × scope), assign multiple roles per user | M |
| FR-014 | Org-hierarchy view (tree), filterable | M |
| FR-015 | Offboarding workflow: deactivate user, list orphaned tasks for reassignment | M |
| FR-016 | Department-head change and manager change with effective date; history preserved | M |
| FR-017 | **Admin role** owns all organization setup (employees, departments, hierarchy, roles, settings); Owner/CEO/Manager do not | M |
| FR-018 | Departments: add, rename, activate/deactivate, delete (only if empty and not a system department), set head (optional regroup of members under the head), control sign-up visibility | M |
| FR-019 | **Self sign-up** (any email address, rate limited; no domain restriction by decision); new account is `employee`, `pending_setup`, in the hidden Unassigned department | M |
| FR-019b | **First-login onboarding**: employee selects department + designation; placed under the department head, else under the Manager; nothing else is accessible until done | M |
| FR-019c | Moving an employee to another department regroups them under that department's head (else the Manager); a department head cannot be moved out without first changing the head | M |

### Projects
| FR-020 | CRUD projects (name, code, department, owner, dates, status); optional on tasks | M |
| FR-021 | Project members (who may be assigned tasks in project) | S |

### Tasks
| ID | Requirement | P |
|---|---|---|
| FR-030 | Create task with fields in §5 of requirements (title, description, project, department, assignee, assigned_by, priority, assigned/start/due, estimate, attachments, instructions, category, type) | M |
| FR-031 | Assignment only within caller's scope and downward rank (Q2); validated server-side | M |
| FR-032 | Task list with filters (status, priority, assignee, dept, project, due range, overdue, blocked), sort, saved views, pagination | M |
| FR-033 | Task detail: overview, activity timeline, comments, time logs, deadline history, delay reasons, blockers, attachments | M |
| FR-034 | Edit task fields (title/description/priority/estimate…) by authorized roles; every change audited | M |
| FR-035 | Reassign task (history in `task_assignments`); timer on old assignee force-stopped | M |
| FR-036 | Status transitions enforced by state machine (§3), with mandatory-data guards | M |
| FR-037 | Priority change with audit + notify | M |
| FR-038 | Acknowledge assignment (records timestamp → "assignment-to-ack" latency) | M |
| FR-039 | Progress update (0–100 %, note) — append-only | M |
| FR-040 | **Mark Complete** by the assignee with a *completion assurance* (summary of work done, "tested: yes/no", test notes/evidence link, optional attachment). Guards: no open blocking blockers; time logged or justification | M |
| FR-041 | **Verify** (optional): Manager/Dept Head/CEO/Owner/assigner marks a completed task as verified (`verified_at/by`) | M |
| FR-042 | **Revert**: Manager/Dept Head (own dept)/CEO/Owner moves Completed → Reopened with mandatory reason code (qa_defect, incomplete, requirement_change, other), note, optional evidence; employee notified; `revert_count++`. Possible at any time after completion (e.g. QA finds the feature broken) | M |
| FR-042b | Per task type/project `requires_review` (default **off**): when on, the assignee uses *Submit for review* (→ Under Review) and only a reviewer can complete | M |
| FR-042c | Completion assurance and every revert are append-only and visible to the employee | M |
| FR-043 | Cancel task (reason mandatory; stops timers, reminders) | M |
| FR-044 | Reopen completed task (authorized, reason mandatory); reminders re-arm against a (new/existing) deadline | M |
| FR-045 | Attachments: upload/download with allow-list, size limit, virus-scan hook, authorization-checked download | M |
| FR-046 | Sub-tasks / dependencies (parent_task_id; `depends_on`) | C |
| FR-047 | Task watchers (extra notification recipients) | S |

### Deadlines
| FR-050 | `original_due_at` immutable; `due_at` current; every change appends history (old, new, actor, reason, timestamp) | M |
| FR-051 | Deadline edit permission by role+scope; employees can only *request* an extension | M |
| FR-052 | Extension request by employee → approve/reject by authorized manager | S |
| FR-053 | Dashboard shows original, current, extension count, history | M |
| FR-054 | Reminder schedule invalidated/recomputed on deadline change (version counter `deadline_version`) | M |

### Reminders, overdue, escalation
| FR-060 | Rules table: offsets (−24h, −2h, 0, +1d, +3d, +7d), channels, recipients; editable by Admin | M |
| FR-061 | Scanner job every minute; idempotent; writes `reminder_log` with unique key | M |
| FR-062 | Overdue flag set automatically when due passes and status ∈ open set | M |
| FR-063 | No reminders for Completed/Cancelled/On Hold(paused by manager)/Under Review (configurable) | M |
| FR-064 | Quiet hours / digest for email (Q7) | S |

### Delay explanations
| FR-070 | Overdue banner + blocking modal on task open until explanation submitted (cannot be permanently dismissed) | M |
| FR-071 | Fields: reason, progress %, work done, remaining work, blockers, expected completion date, optional attachment | M |
| FR-072 | Append-only: no edit/delete by anyone except via new entry; timestamps server-side | M |
| FR-073 | Additional updates allowed any time; re-required per Q13 | M |
| FR-074 | Manager decisions: accept, request clarification, reject, approve revised deadline, escalate — each recorded; accept ≠ complete | M |
| FR-075 | Task stays flagged `overdue` + `delay_explanation_missing` until first explanation | M |

### Time tracking
| FR-080 | Start / pause / resume / stop; each creates/closes `task_time_logs` session row with server UTC timestamps | M |
| FR-081 | One active timer per employee (DB unique + transaction); starting another prompts "switch" (auto-stops previous) | M |
| FR-082 | No overlapping sessions for same employee (incl. manual entries) | M |
| FR-083 | State survives refresh/close/offline (state is server-side; UI re-hydrates) | M |
| FR-084 | Forgotten-timer handling per §6 (check-ins, hard cap, provisional auto-closed time) | M |
| FR-088 | Deadline input: date + "EOD" (default, resolves to `eod_time` = **18:30** in company timezone) or exact time; stored as UTC | M |
| FR-089 | **Work calendar**: company hours 09:30–13:30 and 14:00–18:30 (break 13:30–14:00); every Sunday off; 2nd & 4th Saturday off (nth-weekday rule); other Saturdays working; + holidays; used for capacity, working-day escalation offsets, email send windows; warning when a deadline falls on a non-working day | M |
| FR-089b | Per-employee capacity (default **8.5** productive h/working day; the 13:30–14:00 break is excluded from capacity and timer-hint logic, but a running timer is not auto-paused for the break) and leave marking | M |
| FR-085 | Manual entry/correction as request → approval; every correction audited with before/after | M |
| FR-086 | Metrics: estimated, active, elapsed (assigned→now/completed), assign→start latency, blocked time | M |
| FR-087 | Blocked/On-Hold: timer auto-paused, pause reason recorded | M |

### Blockers & communication
| FR-090 | Raise blocker: type, description, impact, expected resolution, blocks-work flag, mentions | M |
| FR-091 | Blocker status: Open → Acknowledged → In Progress → Resolved → Closed (+ history) | M |
| FR-092 | Manager actions: reply, assign owner, resolve, escalate, extend deadline (links to FR-050) | M |
| FR-093 | Blocking blocker → task Blocked, timer paused; resolved → returns to previous status | M |
| FR-094 | Task comments/questions with @mentions, attachments; types: comment, question, clarification | M |
| FR-095 | Waiting time vs active time distinction in reports | M |

### Notifications
| FR-100 | In-app notification center (list, unread count, mark read, mark all) | M |
| FR-101 | Real-time delivery via WebSocket, fallback to polling | M |
| FR-102 | Email via SMTP, templates, logs, retry w/ backoff, bounce marking | M |
| FR-103 | Recipient resolution engine from `notification_rules` + hierarchy; de-duplicate per (event, user); exclude actor; respect user preferences (mandatory events can't be muted) | M |
| FR-104 | Per-user preferences (channel × event) | S |
| FR-105 | Daily digest email (manager: overdue + blockers) | S |

### Dashboards & reports
| FR-110 | Role-specific dashboards (§13 of brief) with filters | M |
| FR-111 | 12 reports (§14) with filters; export CSV (M), XLSX (M), PDF (S) | M/S |
| FR-112 | Workload indicator (Normal/High/Overloaded) per Q8 | M |
| FR-113 | Reports separate: completion, on-time rate, active hours, elapsed time. No composite score | M |

### Audit & admin
| FR-120 | Append-only `activity_logs` for every important mutation (actor, entity, action, before/after JSON, IP, UA) | M |
| FR-121 | System settings: company timezone, reminder rules, review defaults, capacity defaults, upload limits | M |
| FR-122 | Audit log viewer (Owner/CEO/Admin) with filters | S |

## 3. Task status model (revised)

Stored statuses: **Assigned, Acknowledged, In Progress, On Hold, Blocked, Under Review, Completed, Reopened, Cancelled.**
Derived flags: `is_overdue`, `delay_explanation_missing`, `is_blocked_by_open_blocker`.

Changes vs your list: **Overdue** → derived flag (orthogonal); **Pending** → removed/dashboard group; *Reopened* behaves as "Assigned-again" (employee must re-acknowledge or can start directly).

Terminal states: Completed (reopen possible), Cancelled (reopen only by Owner/CEO).

| From → To | Actor | Guards |
|---|---|---|
| (new) → Assigned | creator | assignee in scope, due_at > now, estimate > 0 |
| Assigned → Acknowledged | assignee | — |
| Assigned/Acknowledged/Reopened → In Progress | assignee | no other active timer unless switching; starts timer |
| In Progress → On Hold | assignee (reason) or manager | timer auto-paused; reminders suppressed per rule |
| On Hold → In Progress | assignee/manager | — |
| In Progress → Blocked | system (blocking blocker opened) or assignee | open blocker exists |
| Blocked → previous | system (blocker resolved/closed) | no other open blocking blockers |
| In Progress → Completed | assignee | **only if `requires_review = false`** (default); completion assurance, no open blocking blockers, time logged or justification; if overdue, a delay explanation exists |
| In Progress → Under Review | assignee | only when `requires_review = true` (or assignee asks for a review voluntarily); same guards as above |
| Under Review → Completed | reviewer | reviewer in scope, ≠ assignee (unless Owner) |
| Under Review → Reopened | reviewer | comment mandatory |
| Completed → Reopened (**Revert**) | Manager / Dept Head (own dept) / CEO / Owner | reason code + note mandatory; allowed any time (QA findings) |
| Completed → Verified (flag, not a status) | reviewer roles / assigner | optional |
| any open → Cancelled | assigner/authorized mgr | reason mandatory |
| Cancelled → Assigned (restore) | Owner/CEO | reason |

Everything else → **HTTP 409 `INVALID_TRANSITION`**. Each transition writes `task_status_history`.

## 4. Non-functional requirements
| ID | Requirement |
|---|---|
| NFR-001 | **API security**: every endpoint authenticates + authorizes server-side (permission + scope + object check); deny by default |
| NFR-002 | Passwords hashed with argon2id; secrets only in env/secret store |
| NFR-003 | Rate limiting: login 5/min/IP+account, API 100/min/user, uploads 20/min |
| NFR-004 | OWASP ASVS L2 targeted; no IDOR (object-level auth tests for every resource) |
| NFR-005 | All timestamps UTC `DATETIME(6)`; ISO-8601 with `Z` in API; render in user TZ |
| NFR-006 | p95 API latency < 300 ms for list/detail at 200 users / 50k tasks; dashboards < 1.5 s |
| NFR-007 | Availability 99.5% business hours; graceful degradation if Redis/SMTP down (outbox keeps events) |
| NFR-008 | Background jobs idempotent, retried with exponential backoff, dead-letter visible to Admin |
| NFR-009 | *(Deferred with hosting)* Backups, PITR and restore drills — not in current scope |
| NFR-010 | Audit data immutable (app role has no UPDATE/DELETE on `activity_logs`, history tables) |
| NFR-011 | Accessibility WCAG 2.1 AA for core flows; keyboard operable |
| NFR-012 | Responsive from 360 px; desktop-first for management screens, mobile-first for employee screens |
| NFR-013 | Observability: structured JSON logs w/ request-id, Sentry-compatible error tracking, health + metrics endpoints |
| NFR-014 | Test coverage: ≥ 80% services layer, 100% of permission-matrix cells covered by automated tests |
| NFR-015 | Migrations via Alembic only, forward + rollback tested; zero manual DDL |
| NFR-016 | File storage outside web root, random names, served via authorized endpoint |
| NFR-017 | Privacy: employees see exactly the time/delay data management sees about them |
| NFR-018 | OpenAPI is the single API contract; frontend client generated from it |
| NFR-019 | Data retention & export per Q16; soft-delete for org entities |
| NFR-020 | Clock: single source of time = DB/app UTC server; client time never trusted |

## 6. Forgotten-timer rule (Q9, normative)
Constraint: closing the browser must **not** stop the timer (developers work in IDEs with the tab closed), so inactivity alone never stops a timer.
1. **Check-ins:** after 4 h and again at 8 h of one continuous session, **and at 19:00 company time** (30 min after close of day) if still running, the employee gets an in-app + email prompt "Still working on <task>?" with one-click **Continue** / **Stop now**. Continue resets the continuous-session clock for check-in purposes.
2. **Hard cap:** if no response, the session is auto-closed at **10 h continuous** or **22:00 company time**, whichever is first (`source=auto_closed`, `end_reason=auto_timeout`). Cap values are settings.
3. **Provisional time:** auto-closed time counts in "active hours" but is labelled *provisional* in every report until confirmed; reports can show confirmed vs provisional separately.
4. **Employee confirmation (next login):** a prompt shows the session with a *suggested end time* = last observed activity (last heartbeat or API call by that user; heartbeat sent every 5 min while the app is open — used only as a hint). Employee may **shorten** the session (move end earlier) with no approval — it can only reduce hours; any **extension** or manual added time needs manager approval (FR-085). Confirmation flips it to confirmed.
5. **Unconfirmed after 3 days:** manager receives one notification; manager can confirm, trim or reject (rejected time is excluded, audited).
6. All changes keep the original log row and write `task_time_corrections` + audit entries. The timer never silently back-dates time.

## 5. Deadline, time-tracking, reminder rules (normative summary)
- `due_at` changes only through `POST /tasks/{id}/deadline` (permission `task.deadline.edit` in scope) with reason ≥ 10 chars; increments `deadline_version`.
- Active time = Σ closed sessions + open session up to now, **excluding** Blocked/On-Hold intervals. Elapsed = (completed_at or now) − assigned_at. Blocked time = Σ blocking blocker intervals.
- Reminder key = `(task_id, rule_id, deadline_version, assignee_id)` UNIQUE; send path = insert-then-send (insert failure ⇒ skip).
