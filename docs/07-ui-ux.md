# Document 7 — UI/UX Plan

## 1. Visual direction
Light, calm SaaS (Linear/Asana-like density, Jira-like rigor, ClickUp-like views). 14 px base, Inter font, 8 px spacing grid, 12 px card radius, subtle borders over shadows. Tokens in Tailwind theme + CSS variables (dark mode possible later).

| Meaning | Colour | Badge text |
|---|---|---|
| Primary / actions | Indigo 600 | — |
| Assigned / Acknowledged / On Hold (the "Pending" group) | Slate/Grey | Assigned… |
| In Progress | Blue 500 | In Progress |
| Under Review | Purple 500 | Under Review |
| Completed | Green 600 | Completed |
| Overdue (flag, shown *beside* status) | Red 600 | Overdue · 2d |
| Blocked | Orange 500 | Blocked |
| Reopened | Amber 500 | Reopened |
| Cancelled | Grey strikethrough | Cancelled |
Priority chips: Critical (red solid), High (orange), Medium (blue), Low (grey). Never colour alone — always icon + text (accessibility). Charts via Recharts with a colourblind-safe palette and consistent status colours.

## 2. Screens (22) and who sees them
| # | Screen | Roles |
|---|---|---|
| 1 | Login | public |
| 2 | Forgot / Reset Password | public |
| 3–7 | Owner / CEO / Manager / Dept Head / Employee Dashboard | per role |
| 8 | Employee Management (list, edit, offboard) — **Administration section** | Owner, CEO(cfg) |
| 9 | Department Management — **Administration section** (departments are fixed company setup) | Owner, CEO(cfg) |
| 10 | Organizational Hierarchy (tree + "change manager") — **Administration section** | Owner, CEO(cfg) |
| 10b | My Team / My Department (read-only list, no org setup screens) | Manager, Department Head |
| 11 | Project Management | Owner, CEO, Manager, DeptHead |
| 12 | Task Listing (table / board / calendar) | all (scoped) |
| 13 | Create Task (modal-page) | Owner, CEO, Manager, DeptHead |
| 14 | Task Details | all (scoped) |
| 15 | Time Tracking (my timer, week timesheet; managers: team timesheets, corrections queue) | all |
| 16 | Overdue Tasks (queue) | all (scoped) |
| 17 | Delay Reason Management (review queue / my explanations) | mgmt / employee |
| 18 | Blocker Management | mgmt queue / employee own |
| 19 | Notification Center | all |
| 20 | Reports & Analytics | mgmt (employee: own) |
| 21 | User Profile (tz, password, preferences, MFA) | all |
| 22 | System Settings (reminder/notification rules, review defaults, roles & permissions, capacity, audit log) | Owner (A) |

## 3. Navigation per role (left sidebar, collapsible; top bar = search, "+ New task", timer widget, bell, avatar)

*Decision: organization setup (employees, departments, hierarchy, roles, settings) is not in the Owner/CEO/Manager panels at all. A separate **Admin** role has its own panel for it. Managers and heads get a read-only "My Team / My Department" list; employees get none of these screens. New employees sign up at `/signup` and choose department + designation at first login.*

**Admin** — Dashboard · Employees · Departments · Hierarchy · Roles & Permissions · Settings · (Audit log, Rules later)
**Owner** — Dashboard · Tasks · Overdue · Delay Reviews · Blockers · Projects · Time · Reports · Notifications
**CEO** — Dashboard · Tasks · Overdue · Delay Reviews · Blockers · Projects · Time · Reports · Notifications
**Manager** — Dashboard · My Team (employees, workload) · Tasks · Overdue · Delay Reviews · Blockers · Time (team + corrections) · Projects · Reports · Notifications
**Department Head** — Dashboard · Department (members, workload) · Tasks · Overdue · Delay Reviews · Blockers · Time · Projects · Reports · Notifications
**Employee** — **My Day** (dashboard) · My Tasks · Time · My Blockers · My Explanations · Notifications · Profile *(no org analytics)*

## 4. Layouts

### Management dashboard (Owner/CEO)
Row 1 KPI cards: Employees · Departments · Open · In Progress · Under Review · Completed (period) · **Overdue** · Critical open · **Unresolved blockers**.
Row 2: Tasks by status (stacked bar by department) · Created vs Completed trend (line).
Row 3: Estimated vs Actual hours (grouped bar, by dept) · Deadline-extension stats (count per task, top extended) ·  On-time completion rate (shown *beside* active hours, never merged into a score).
Row 4: Employee workload heat list (Normal/High/Overloaded bars) · Latest delay explanations (awaiting review) · Recent activity feed.
Sticky filter bar: Department · Employee · Manager · Priority · Status · Date range · Project · "Save view". Cards are clickable → pre-filtered Task List.

### Manager / Dept Head dashboard
Left: **Needs your attention** (explanations to review, completions to review, open blockers, orphaned/unassigned, extension requests). Right: team workload table, tasks by status, overdue list, time-tracking summary (est vs active this week). Dept Head view identical but department-scoped + department productivity (completion, on-time, active hrs shown as separate metrics).

### Employee dashboard — "My Day"
Single column, mobile-friendly. Order: (1) **red banner** if any overdue task lacks explanation (click → opens form), (2) **Active timer card** (task, elapsed, Pause/Stop), (3) **Do this next** — tasks auto-sorted (see §6), (4) New assignments awaiting acknowledgement, (5) Upcoming deadlines (7 days), (6) Blocked/On hold, (7) Recently completed. Small "workload" pill ("Normal · 14h of 40h this week"). No management analytics.

### Task creation (full-page form, sticky summary)
Section A *What*: Title, Description (rich text, limited), Category, Type, Project(optional), Attachments, Additional instructions.
Section B *Who*: Department (filters employee list) → Assignee (searchable; shows **workload chip and next-deadline conflicts inline**), Assigned by (read-only = me).
Section C *When*: Priority, Assignment date (read-only now), Start date, Deadline (date+time, tz shown), Estimated hours.
Section D *Process*: Requires review (default from project/type), watchers.
Right rail: live "impact" panel — assignee's current open tasks, hours, conflicts ("3 tasks due the same day, 22 h estimated vs 16 h capacity").
Validation: client (Zod) mirrors server; due > now; estimate > 0; server authoritative.

### Task details (two columns)
Header: `TSK-000123 · title`, status badge + Overdue/Blocked flags, priority, assignee, **action bar driven by `allowed_actions`** (Acknowledge/Start/Pause/Submit/…; manager: Review, Change deadline, Priority, Reassign, Cancel).
Left: Description & instructions, Progress (bar + update composer), Tabs — **Activity** (unified timeline) · Comments & Questions · Time · Deadlines · Delay Explanations · Blockers · Files.
Right sidebar: assignee/assigner/dept/project; **Deadline card** (original, current, extensions ×N, expandable history with who/why); **Time card** (Estimated 12h · Active 9h · Elapsed 4d · Blocked 1d · assign→start 3h; donut/bar); Watchers; Dates.
Overdue state: red band at top + modal gate for the assignee until an explanation is submitted (can be minimised, reappears on next navigation/refresh — not dismissible).

### Task list
Table (default) with column chooser, saved views, bulk actions for managers (priority, reassign); Board (by status); Calendar (by due date). Row shows priority chip, status, flags, assignee avatar, due (relative + absolute), progress, est/actual.

### Time tracking
Employee: today's sessions, week grid, "add missed time" request. Manager: per-employee timesheet, auto-closed/flagged sessions, corrections queue with before/after diff.

### Notification center
Tabs All/Unread/Mentions/Alerts, grouped by day, click → deep link; mark all read; bell dropdown for latest 8.

## 5. Responsive & accessibility
Breakpoints 360 / 768 / 1024 / 1440. Sidebar → bottom/drawer nav < 768. Tables → card list on mobile; employee screens designed mobile-first, management dashboards desktop-first but usable on tablet. Touch targets ≥ 44 px, focus rings, ARIA labels on icon buttons, live regions for toasts, full keyboard flow for forms/modals, WCAG AA contrast, `prefers-reduced-motion`. Empty states, skeleton loaders, optimistic updates only for safe actions (comments, mark read); transitions & timers wait for server confirmation.

## 6. Priority-based sort ("what do I do first")
Server-computed order for `My Tasks`:
1. Overdue first (oldest overdue first)
2. then `manual_rank` if a manager pinned an order
3. then priority (Critical > High > Medium > Low)
4. then `due_at` ascending
5. then `assigned_at` ascending.
Plus "At risk" hint: remaining estimate (est − active) > time left until deadline × capacity. Workload bands (Q8): ≤ 80% Normal, 80–100% High, > 100% Overloaded. Overdue alone never marks someone unproductive: the UI always shows the blocker/approved-extension/workload context beside overdue counts.

## 7. UX principles for the accountability features
- Employee sees what management sees about them (transparency, NFR-017).
- Delay form is short, pre-filled with current progress, one screen; submit takes < 1 minute.
- Destructive/critical actions (cancel, deadline change, reject) require reason with confirmation dialog that states who will be notified.
- Tone of copy is neutral ("Your deadline has passed. Let your team know where things stand."), not punitive.
