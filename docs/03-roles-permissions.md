# Document 3 — Role & Permission Matrix

## 0. Admin role — DECISION (supersedes the Owner/CEO "manage" cells in §3)

Organization setup is **not** an Owner/CEO job. A separate **Admin** role (rank 110, no task authority) owns it, and the Admin panel is the only place it appears:

| Admin only (org-wide) | Not available to Owner / CEO / Manager / Head / Employee |
|---|---|
| Employees: create, edit, deactivate, change role/department | `employee.manage` |
| Departments: add, rename, activate/deactivate, **delete** (only when empty), set heads, control sign-up visibility | `department.manage` |
| Hierarchy: reporting lines, regroup members under a head | `hierarchy.manage` |
| Roles & permissions, system settings (timezone, EOD), reminder/notification rules | `role.manage`, `settings.manage`, `notification.rules.manage` |

Owner and CEO keep full **work** authority (assign, deadlines, priorities, verify/revert, delays, blockers, reports). The **audit log is Admin-only** (`audit.view`, [ADR 002](adr/002-role-emails-and-no-owner-ceo-audit.md)); Owner and CEO do not have it. Admin also has `employee.view`. Rank guard: nobody manages a user who outranks them, so only an Admin can manage Admin/Owner/CEO accounts.

**Role emails.** The Admin registers the email of each Owner, CEO or Manager (*Administration > Role emails*). Whoever signs up with exactly that email gets the role automatically and skips onboarding (joins Management; CEO reports to Owner, Manager to CEO). Everyone else is an Employee. **Department heads** are chosen on the Departments screen; naming a head also grants the Department Head role, and the replaced head loses it unless they head another department. See ADR 002 (including the accepted risk that sign-up does not yet verify email ownership).

**New employees** self-register (`/signup`, any email address, rate limited), land in a hidden *Unassigned* holding department with status `pending_setup`, and at first login must choose **department + designation**. They are then placed under that department's head, or under the Manager if the department has none (Support, Sales, Accounts). Until onboarding is done the API allows nothing else. Admins can also finish a pending employee's setup from the Employees screen.

## 0b. Heads in the loop, peer assignment, and delay-reason approval — DECISIONS (Phase 8)

1. **Department Head in the loop.** Whoever assigns work to a department's employee (Owner, CEO, Manager, or a peer Head), that department's Head is notified, can see the task (scope D), and may press **Take ownership** once per task. Ownership is an append-only record (who, when, note) shown in the task's *Accountability* card and notifies the assignee, assigner and Manager.
2. **Head → Head assignment.** Department Heads may assign tasks to each other across departments (never to other staff outside their department, never upward). When they do, the other Head, the Manager above both, the CEO and the Owner are notified (rules editable by the Admin).
3. **Overdue reasons are approved by the line first.** The employee's explanation goes only to their Department Head and the Manager (and the assigning Manager/Head). It is **invisible to the CEO and Owner** (task screens, queues, dashboards, reports, notifications) until a Head/Manager decides *Accepted*, *Revised deadline approved* or *Escalated*. Clarification-requested or rejected reasons are never shown to leadership. On release a `DELAY_RELEASED` notification reaches the CEO and Owner; *Escalated* additionally lets the CEO/Owner decide on it. Employees with no Head (Support, Sales, Accounts) are reviewed by the Manager.

## 1. Recommended model: RBAC + Scope (a combination, with each part doing one job)

| Mechanism | Answers | Stored in |
|---|---|---|
| **RBAC** | *What* actions may this user perform? | `roles`, `permissions`, `role_permissions`, `user_roles` |
| **Reporting relationships** | *Whose* work is "my team"? (subtree, effective-dated) | `reporting_relationships` |
| **Department membership** | *Which department's* work? | `employees.department_id`, `departments.head_employee_id` |

Each `role_permissions` row carries a **scope**: `self` ⊂ `team` ⊂ `department` ⊂ `organization`.
Authorization = `has_permission(user, code)` **AND** `target ∈ resolve_scope(user, permission.scope)` **AND** object-state rules (e.g. status machine).

Why not only RBAC: "Manager" couldn't be limited to their people. Why not only reporting lines: Support/Sales/Accounts have no head, and department heads need department-wide reach. Why not only departments: Owner/CEO cross all, managers cross several.

Scope resolution:
- `organization` → no filter.
- `team` → employees in the **recursive subtree** of the user's `reporting_relationships` (MySQL 8 recursive CTE; cached per request, invalidated on hierarchy change) **∪** employees of departments explicitly mapped to the user (`manager_departments`) — see Q1.
- `department` → `employees.department_id IN (user's headed departments ∪ user's own department if granted)`.
- `self` → own tasks (assignee_id = me) or items I created.

A user may hold multiple roles; effective permission = **union**, widest scope wins per permission.

Rank rule: `roles.rank` (Owner 100, CEO 90, Manager 70, Dept Head 50, Employee 10). Assignment, review and override actions check `actor.max_rank ≥ target.max_rank` (Q2). Ranks are config, not code.

## 2. Permission codes
`task.view`, `task.create`, `task.assign`, `task.edit`, `task.reassign`, `task.priority.change`, `task.deadline.edit`, `task.review`, `task.cancel`, `task.reopen`, `task.ack/start/update/submit` (assignee-only actions, always `self`), `time.view`, `time.correct.approve`, `delay.view`, `delay.review`, `blocker.view`, `blocker.manage`, `comment.create`, `report.view`, `report.export`, `dashboard.org|team|dept|self`, `employee.view`, `employee.manage`, `department.manage`, `hierarchy.manage`, `role.manage`, `project.manage`, `settings.manage`, `audit.view`, `notification.rules.manage`.

## 3. Matrix (seed defaults)
Legend: **O** = organization · **T** = team (reporting subtree) · **D** = own department · **S** = self (own tasks / created by me) · **—** = none · (A) = Admin capability required.

| Capability | Owner | CEO | Manager | Dept Head | Employee |
|---|---|---|---|---|---|
| View tasks | O | O | T | D | S |
| Create tasks | O | O | T | D | — (Q3) |
| Assign tasks (to) | anyone | anyone ≤ CEO rank | T incl. Dept Heads | D employees | — |
| Edit task fields | O | O | T | D (tasks they created or in dept) | S: only own description notes/progress, never deadline/priority/assigner |
| Reassign | O | O | T | D | — |
| Edit deadline | O | O | T | D | — (may request) |
| Change priority | O | O | T | D | — |
| Acknowledge/start/pause/stop/progress/**mark complete** (with assurance) | — | — | — | — | S (own tasks) |
| Verify (optional) / **Revert** completed tasks (QA findings) | O | O | T | D | — |
| Cancel / reopen | O | O | T | D (reopen: own dept) | — |
| View time logs | O | O | T | D | S |
| Approve time corrections | O | O | T | D | — (can *request* for S) |
| View delay explanations | O | O | T | D | S |
| Submit delay explanation | — | — | — | — | S |
| Review delay explanation | O | O | T | D | — |
| View blockers | O | O | T | D | S |
| Raise blocker | O | O | T | D | S |
| Resolve/assign/escalate blockers | O | O | T | D | — (can close own after resolution confirm: no) |
| Comment / ask questions | O | O | T | D | S |
| View dashboards | Owner dash (O) | CEO dash (O) | Manager (T) | Dept (D) | Employee (S) |
| View reports | O | O | T | D | S (own time/task only) |
| Export reports | O | O | T | D | S |
| Manage employees | O (A) | O (A, configurable) | — | — | profile self-edit only |
| Manage departments / hierarchy | O (A) | O (A, configurable) | — | — | — |
| Manage roles & permissions | O (A) | — | — | — | — |
| Manage projects | O | O | T | D | — |
| System settings / reminder & notification rules | O (A) | — | — | — | — |
| View audit log | A only | — | — | — | — |

Key separations (your rule 10): **Department Head cannot see other departments** (scope D); **Manager cannot see outside T**; **Employees see only S**; **Owner/CEO org-wide**. The CEO gets no `role.manage`/`settings.manage` by default (separation of duties); toggle in the UI if wanted.

## 4. Object-level rules (beyond the matrix)
1. A reviewer may not approve their own submitted work (unless Owner).
2. Task visible to a user if: assignee, assigner, in scope, or watcher/mentioned (read-only on that task).
3. Comments flagged `visibility = managers_only` are hidden from the employee (default off; employee sees everything about themselves — NFR-017).
4. Attachment download re-checks task visibility every time.
5. Deactivated users keep history but cannot authenticate; their tokens are revoked immediately.
6. Every denial of a privileged action is logged (`activity_logs`, action `AUTHZ_DENIED`).

## 5. Test strategy (anti-regression)
The matrix above is encoded in `tests/permissions/matrix.yaml` → a parametrized pytest generates one test per (role, capability, in-scope/out-of-scope) cell. A PR that changes authorization must change the YAML and is flagged for human review.
