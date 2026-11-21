# Document 6 — API Plan

Base: `/api/v1` (versioned; your examples used `/api/...`). JSON, ISO-8601 UTC (`2026-11-20T12:30:00Z`). Auth: `Authorization: Bearer <access>` except `/auth/*`. Pagination: `?page=1&page_size=25` → `{items,total,page,page_size}`; sorting `?sort=-due_at`. Errors: `{code,message,details,request_id}`. Mutations that must not double-submit accept `Idempotency-Key`. Every endpoint lists the permission it enforces (**scope-checked server-side**).

Changes from your sample list: actions are `POST /tasks/{id}/<verb>` (state transitions, not field PUTs); `PUT /tasks/{id}/deadline` becomes `POST` (it appends history, it does not replace a resource); `PATCH` for partial edits.

## Auth & profile
| Method | Path | Notes |
|---|---|---|
| POST | /auth/login | rate-limited; returns access token, sets refresh cookie |
| POST | /auth/refresh | rotates |
| POST | /auth/logout · /auth/logout-all | revoke |
| POST | /auth/forgot-password · /auth/reset-password | generic response |
| POST | /auth/change-password | |
| POST | /auth/mfa/enroll · /auth/mfa/verify | S |
| GET | /auth/me | user, employee, roles, effective `{permission: scope}` map |
| PATCH | /me/profile · /me/preferences | tz, notification prefs |

## Organization
| Method | Path | Permission |
|---|---|---|
| GET/POST | /employees | employee.view / employee.manage |
| GET/PATCH | /employees/{id} | |
| POST | /employees/{id}/deactivate · /reactivate | employee.manage; deactivate returns orphaned-task list |
| GET | /employees/{id}/workload | dashboard.* in scope |
| GET/POST | /departments · GET/PATCH /departments/{id} | department.manage |
| PUT | /departments/{id}/head | department.manage (history logged) |
| GET | /hierarchy/tree | tree within scope |
| GET | /hierarchy/relationships?employee_id= | |
| POST | /hierarchy/relationships | set/change manager (closes previous row) — hierarchy.manage |
| GET/POST/PATCH | /roles · /roles/{id} · PUT /roles/{id}/permissions | role.manage |
| GET | /permissions | |
| PUT | /users/{id}/roles | role.manage |
| GET/POST/PATCH | /projects · /projects/{id} ; GET/PUT /projects/{id}/members | project.manage |
| GET/POST/PATCH | /task-categories · /task-types | settings.manage |

## Tasks
| Method | Path | Notes |
|---|---|---|
| GET | /tasks | filters: status, priority, assignee_id, department_id, project_id, overdue, blocked, due_from/to, q, assigned_by |
| POST | /tasks | task.create + task.assign (assignee in scope/rank) |
| GET | /tasks/{id} | task.view; includes derived `is_overdue`, time summary, permitted actions list |
| PATCH | /tasks/{id} | task.edit; field-level permission (deadline/priority excluded) |
| POST | /tasks/{id}/reassign | task.reassign |
| POST | /tasks/{id}/priority | task.priority.change `{priority, reason?}` |
| POST | /tasks/{id}/acknowledge | assignee |
| POST | /tasks/{id}/start | assignee; starts timer (`{switch: true}` to auto-stop another) |
| POST | /tasks/{id}/pause · /resume · /stop | assignee; stop ends session w/o status change |
| POST | /tasks/{id}/hold · /unhold | assignee/manager, reason |
| POST | /tasks/{id}/progress | `{progress_pct, note}` |
| POST | /tasks/{id}/complete | assignee; body = completion assurance `{summary, tested, test_notes?, evidence_url?}`; only when `requires_review=false` |
| POST | /tasks/{id}/submit-for-review | assignee; only when `requires_review=true` (or voluntary) |
| POST | /tasks/{id}/verify | optional; reviewer roles/assigner — marks verified |
| POST | /tasks/{id}/revert | Manager/Head/CEO/Owner; `{reason_code, reason, found_by?, evidence?}` → Reopened |
| POST | /tasks/{id}/review | only for review-required tasks: `{decision: approve|reject, comment}` |
| GET | /work-calendar?from&to | working days/hours resolved from rules + holidays |
| POST | /tasks/{id}/cancel · /reopen | reason mandatory |
| GET | /tasks/{id}/timeline | merged activity feed |
| GET | /tasks/mine | employee view, server-sorted by priority engine |
| POST/GET/DELETE(own, before submit n/a) | /tasks/{id}/attachments · GET /attachments/{id}/download | authz re-checked |
| POST/GET | /tasks/{id}/watchers | S |

### Built in Phase 3 (implemented, with tests)
`GET/POST /tasks` · `GET/PATCH /tasks/{id}` · `POST /tasks/{id}/reassign|priority|cancel|acknowledge` · `GET /tasks/{id}/timeline` · `POST /tasks/{id}/attachments` · `GET /attachments/{id}/download` · `GET /workload` (people you can assign to, with open tasks by priority/status, overdue, hours vs 7-day capacity, level) · `GET/POST/PATCH /projects` · `GET /task-meta`.
Task list accepts `status, priority, assignee_id, department_id, project_id, assigned_by_id, overdue, open, mine, due_from, due_to, q, page, page_size` and returns open tasks first, then overdue → priority → deadline.
Create body: `due_date` + optional `due_time` (company time; omitted = end of day 18:30) — not a UTC timestamp.

### Built in Phase 4 (implemented, with tests)
Task actions: `POST /tasks/{id}/start|pause|stop|hold|unhold|progress|complete|submit-for-review|review|verify|revert` · `GET /tasks/{id}/time`.
Time: `GET /time/active` · `POST /time/heartbeat` · `POST /time/checkin/continue` · `GET /time/unconfirmed` · `POST /time/logs/{id}/confirm` (shorten only) · `POST /time/logs/{id}/adjust` (manager) · `GET /time/logs` (scoped) · `POST/GET /time/corrections` · `POST /time/corrections/{id}/decision` · `GET /me/workload` · `POST /admin/jobs/timer-guard`.
Timestamps in requests are ISO-8601 with a zone (`Z`); the server stores UTC and never trusts browser clocks for timer start/stop.

### Built in Phase 5 (implemented, with tests)
`POST /tasks/{id}/deadline` (due_date, optional due_time, reason) · `GET /tasks/{id}/deadline-history` · `POST /tasks/{id}/extension-requests` · `GET /extension-requests` · `POST /extension-requests/{id}/decision` · `GET /stats/deadlines` · `POST /tasks/{id}/delay-reasons` · `GET /tasks/{id}/delay-reasons` · `POST /delay-reasons/{id}/review` · `GET /delays/queue`.
Task detail now carries `deadline` (original, current, version, extension count, history, requests) and `delay` (overdue, required + why, awaiting review, escalation level, explanations with decisions). Completing/submitting an overdue unexplained task returns 409 `DELAY_EXPLANATION_REQUIRED` unless `late_reason` is supplied.

### Built in Phase 6 (implemented, with tests)
`GET /notifications` · `GET /notifications/unread-count` · `PUT /notifications/{id}/read` · `POST /notifications/read-all` · `GET/PUT /me/notification-preferences`  (no WebSocket: the page polls `unread-count` every 20 s) · Admin: `GET/PATCH /admin/notification-rules`, `GET/PATCH /admin/reminder-rules`, `GET /admin/email-logs`, `POST /admin/email-logs/{id}/retry`, `GET /admin/jobs/status|failures`, `POST /admin/jobs/run-now`.

### Built in Phase 7 (implemented, with tests)
Blockers: `POST/GET /tasks/{id}/blockers` (raise: assignee only, `blocker.raise`) · `GET /blockers?status&open&page` (scoped queue, `blocker.view`) · `GET /blockers/{id}` · `POST /blockers/{id}/acknowledge|assign|start|reply|resolve|close|reopen|escalate` (manager actions need `blocker.manage` in scope; the assigned owner may start/resolve; the raiser may close/reopen). Each response carries `actions` computed server-side. A blocker that stops work moves the task to `blocked`, stops the timer and is restored to the previous status when the last blocking blocker clears. `GET /tasks/{id}` adds `blockers`, `open_blockers` and `time.blocked_seconds`.
Discussion: `GET/POST /tasks/{id}/comments` (`kind` comment|question|clarification, `parent_id` for replies, `mentions` user ids) · `GET /tasks/{id}/mentionable` · `PATCH /comments/{id}` (author only, 10 minutes). Comments are never deleted.

## Deadlines & delays
| Method | Path | Notes |
|---|---|---|
| POST | /tasks/{id}/deadline | `{new_due_at, reason}` — task.deadline.edit; appends history, bumps version, re-arms reminders, notifies |
| GET | /tasks/{id}/deadline-history | |
| POST | /tasks/{id}/deadline-requests | employee request (S) |
| POST | /deadline-requests/{id}/decision | approve/reject (S) |
| POST | /tasks/{id}/delay-reasons | assignee; full structured payload; append-only |
| GET | /tasks/{id}/delay-reasons | |
| POST | /delay-reasons/{id}/review | `{decision, comment, new_due_at?}` — delay.review; revised deadline calls deadline service |
| GET | /delays/pending | manager queue (explanations awaiting review / missing) |

## Time tracking
| Method | Path | Notes |
|---|---|---|
| GET | /time/active | my active session (app shell widget) |
| GET | /tasks/{id}/time-logs | time.view |
| GET | /time/logs?employee_id&from&to | time.view, scoped |
| POST | /time/corrections | employee/manager manual add or edit request |
| POST | /time/corrections/{id}/decision | time.correct.approve |
| GET | /tasks/{id}/time-summary | estimated/active/elapsed/blocked/assign→start |

## Blockers & comments
| Method | Path | Notes |
|---|---|---|
| POST/GET | /tasks/{id}/blockers | raise / list |
| GET | /blockers | manager queue (status, dept, owner) |
| GET | /blockers/{id} | with events |
| POST | /blockers/{id}/acknowledge · /assign · /reply · /resolve · /close · /reopen · /escalate | blocker.manage; employee may `/reply` on own |
| POST/GET | /tasks/{id}/comments | kind=comment/question/clarification; mentions |
| PATCH | /comments/{id} | author, within 10 min, edit shown; original kept in audit |

## Notifications
| Method | Path | Notes |
|---|---|---|
| GET | /notifications?unread=true | |
| GET | /notifications/unread-count | |
| PUT | /notifications/{id}/read · POST /notifications/read-all | |
| GET/PUT | /me/notification-preferences | |
| GET/POST/PATCH | /admin/notification-rules · /admin/reminder-rules | settings.manage |
| GET | /admin/email-logs · POST /admin/email-logs/{id}/retry | |
| WS | /ws?ticket= | server→client signals |

## Dashboards & reports
| Method | Path |
|---|---|
| GET | /dashboards/owner · /ceo · /manager · /department · /employee (same payload family, scope-filtered; common filters) |
| GET | /reports/{key} — keys: employee-tasks, department-tasks, daily, weekly, monthly, overdue, deadline-extensions, time-tracking, estimate-vs-actual, completion, workload, blockers |
| POST | /reports/{key}/export `{format: csv|xlsx|pdf, filters}` → async job → `GET /exports/{id}` → download |

## Admin
`GET/PATCH /admin/settings` · `GET /admin/audit-logs` (audit.view) · `GET /admin/jobs/failures` · `GET /healthz` `/readyz` (unauthenticated, no data).

## Contract rules
1. Input schemas per action with `extra="forbid"` (no mass assignment).
2. Out-of-scope object → **404** (not 403) to prevent enumeration; in-scope but not permitted action → 403 `FORBIDDEN_ACTION`.
3. `GET /tasks/{id}` returns `allowed_actions: ["start","pause",…]` computed by the same state machine + policy the POST uses → UI never guesses.
4. Optimistic concurrency: task responses carry `version`; mutating calls may send `If-Match`/`version`; 409 `STALE_VERSION`.
5. Rate limits per NFR-003; uploads multipart with server-side type sniffing.


## ADR 006 changes (QA in the loop, date-only deadlines)
- `due_time` and `expected_time` no longer exist on any endpoint; deadlines are dates (end of the working day). Sending them returns 422.
- `POST/PATCH /tasks` accept `head_employee_id` and `qa_employee_id` (optional). `POST/PATCH /projects` accept `qa_employee_id`;
  `POST /projects/{id}/points/{pid}/assign` accepts both. Task and project responses include `head` and `qa`.
- `review_stage` is now `qa | head | leadership`. `POST /tasks/{id}/review` at the `qa` stage: `approve` = bugs solved, goes to the head;
  `reject` (comment required) = bugs found, task is Reopened for the assignee. `GET /tasks?awaiting_my_review=true` includes QA turns.

## ADR 008: one-time code sign-in, employee IDs, department QA
- `POST /auth/login {email,password}` -> with `TMS_OTP_ENABLED=true` (default): `200 {otp_required:true, challenge, email_hint, expires_in, resend_after}` (no session); otherwise the usual tokens.
- `POST /auth/signup` -> same challenge shape (the mailbox is proven before the first session).
- `POST /auth/verify-otp {challenge, code(6 digits)}` -> tokens (same body as a normal sign-in). Errors: 401 wrong/expired/used code; 5 wrong codes end the challenge.
- `POST /auth/resend-otp {challenge}` -> new challenge body; 429 `OTP_TOO_SOON` / `OTP_RESEND_LIMIT`. 503 `OTP_EMAIL_FAILED` when the mail server is down.
- `POST /employees`: `employee_code` is optional (generated as `SW-XXXXXX`); a custom one must have letters and digits, not be a counter such as `EMP-001` (422 `INVALID_EMPLOYEE_CODE`), and be unique (409 `EMPLOYEE_CODE_EXISTS`).
- `PUT /departments/{id}/qa {qa_employee_id|null}` (permission `department.manage`); departments now return `qa_employee_id`.
- Review chain: QA (task > project > department QA) -> head (task > project > assignee's department head) -> CEO/Owner. See ADR 008.
