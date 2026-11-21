# SeaWind Task Management: project overview for QA

For testers who have not seen the system before. Read sections 1 to 4 first (20 minutes), then use sections 5 to 9 as your test plan.

## 1. What the product is
A web app where management assigns work to employees, follows progress against **deadlines**, and gets told (in the app and by email) when something needs attention. Built for the **development team** (it has a QA step), but works for any department.

- **Website and API:** one address, `https://tksb.pro.seawindsolution.com` (website pages and `/api/v1/...`).
- **Sign in:** `/login`: email + password, then a **6-digit code emailed to the registered address** (valid 10 minutes, 5 tries, resend after 30 s). Sign-up needs the code too. The bottom-left text on the sign-in page shows the build date and the API address in use.
- **Fresh install = empty.** The database only has the **Admin** account. Everything else (departments, people, roles, projects, tasks) is created by you during testing.
- **No timer.** Time tracking is switched off: people are measured on deadlines, not hours.
- **No WebSockets.** The notification bell asks the server for the unread count **every 20 seconds** and refreshes when opened.

## 2. Who is who (roles)
| Role | Does | Cannot |
|---|---|---|
| **Admin** | Creates departments, employees, roles, reporting lines; settings; notification rules; audit log | Has no tasks, signs nothing off |
| **Owner** | Everything about work, in the whole company: create/assign tasks and projects, deadlines, final review | Organisation setup (Admin only) |
| **CEO** | Same as Owner for work; final review (either Owner or CEO can complete) | Organisation setup |
| **Manager** | Create/assign tasks and projects for their team (reporting line), deadlines, reviews | Company-wide data; the CEO/Owner final review |
| **Department Head** | Tasks for their department; "Take ownership"; heads/approves work | Other departments |
| **Employee** | Sees and works on **own** tasks only: acknowledge, start, progress, finish, blockers, comments, ask for more time | Create/assign tasks, change deadlines or priority |

Rules to remember: an employee never sees tasks outside their scope (the API answers **404**, not 403, for things you may not see). Nobody reviews or verifies their own work. Tasks cannot be assigned "upward" to someone who outranks you.

## 3. The main flows
### 3.1 A task's life
`Assigned -> Acknowledged -> In progress -> (On hold / Blocked) -> Under review -> Completed`, plus `Reopened` (sent back) and `Cancelled`.
- Finishing needs a short summary and a "tested: yes/no" statement (if not tested, a reason).
- Every task an employee finishes is **reviewed**: QA (task > project > department QA tester) -> head (task > project > the assignee's department head) -> CEO/Owner. A department with no head goes straight to CEO/Owner. Only work done by the Owner or CEO themselves completes directly.

### 3.2 Development flow with QA (the important one)
When a task (or its project) has a **QA tester** and/or **head**:
1. Developer finishes -> status **Under review**, stage **QA**. The QA is notified (app + email).
2. **QA tests.** Found bugs? QA chooses *Report bugs* and describes them (required) -> task is **Reopened** for the developer (mail to everyone in the loop). Developer fixes and submits again -> **back to QA** (full re-test).
3. QA ticks "all bugs solved" -> stage **Head** (notified).
4. Head approves (or sends back) -> stage **CEO / Owner** (both notified).
5. CEO **or** Owner marks reviewed -> **Completed**. Everyone in the loop is told.

Stages with nobody assigned are skipped; the same person is never asked twice; the assignee never reviews their own work. If a QA/head is removed while work waits for them, it moves to the next stage.

### 3.3 Projects
A project has a **mandatory deadline (end date)**, optional start date, expected result, head, QA, team and "points" (planned work that becomes a task when assigned). With a team, tasks can only go to team members. Completed only when every point is assigned and every task is done; the Owner/CEO then marks the project completed. Adding work to a completed project reopens it.

### 3.4 Deadlines, delays, extensions
- A **deadline is a date** (no time). It falls at the end of that working day (18:30 company time). Sending a time is rejected.
- Working calendar: 09:30-13:30 and 14:00-18:30; **Sundays and the 2nd and 4th Saturday are off**; company holidays are set by the Admin. Choosing a non-working day warns but is allowed.
- A task is **late 40 minutes after** its deadline (grace). From then the employee **must explain the delay** to finish it. The explanation goes first to their Department Head/Manager; CEO/Owner only see it after approval.
- Employees cannot change deadlines: they **request an extension**; a manager approves/declines (the original deadline is always kept).

### 3.5 Reminders and escalation (cron job)
Task: 24 h before, 2 h before, at the deadline, then +1, +3 and +7 **working days** after (escalating: employee -> manager line -> CEO -> Owner). Project: the day before, the day of, and once overdue (to everyone on the project; overdue also to CEO and Owner). Reminders stop when the task is finished, cancelled or its deadline changes. They only run if the server's **cron job** runs every minute.

### 3.6 Messages and email
- Comments, questions and replies (edit your own within **10 minutes**) go **in full** to **everyone in the loop**: assignee, assigner, the task's head and QA, and the project's head, QA, team and creator (not to the author). By app notification **and email**.
- Also mailed to the loop: new task, bugs found, completion, blockers raised/replied/resolved.
- Each person gets one notification per event even if they match several rules.
- Mail normally leaves within seconds of the action; if the server has no cron, it is sent right after each change. Failed mails are retried (1 min, 5 min, 30 min, 2 h, 12 h).

## 4. Set up your test data (about 15 minutes)
1. Sign in as the Admin. Create departments (e.g. Developers, QA). Use **real mailboxes you can read** for test users, otherwise you cannot check email.
2. Admin -> *Role emails*: register the Owner, CEO and Manager emails, or create employees directly and assign roles.
3. Create: 1 Owner, 1 CEO, 1 Manager, 1 Department Head, 2 developers, 1 QA tester. Set reporting lines (developers -> head -> manager).
4. Open each account in a separate browser profile or private window (one session per browser).
5. Password rules: at least 10 characters, upper and lower case, a digit.

## 5. Test checklist
Mark each as Pass / Fail / Blocked and note the account used.

**Sign-in and security**
- [ ] Correct login works; wrong password shows "Invalid email or password" (no hint which part is wrong).
- [ ] 5 wrong attempts lock the account for 15 minutes; login is rate-limited.
- [ ] Logout stops everything; the back button does not show private pages; the bell stops polling.
- [ ] Employee opens another person's task URL -> "not found". Employee has no "assign task" menu.
- [ ] Forgot password / sign-up / onboarding (new sign-ups land "pending setup" until they choose department and designation).

**Tasks**
- [ ] Owner/CEO/Manager/Head create a task: deadline is a date only; past dates rejected; assignee limited to who they may assign to.
- [ ] Optional **Head** and **QA** fields on the create form; both can be edited later.
- [ ] Assignee gets a notification and an email with title, priority and deadline.
- [ ] Acknowledge, start, progress (needs a note), hold, resume, raise a blocker.
- [ ] Finish with no head/QA anywhere (e.g. a department without a head) -> goes to CEO/Owner review; with a department head -> head first.
- [ ] Employee IDs look like `SW-7K2QX9` (letters and digits); the Admin cannot save `EMP-001`.
- [ ] OTP: wrong code refused, 5 wrong codes end it, code expires after 10 minutes, resend works after 30 s, mail failure shows a clear message.
- [ ] Reassign, change priority, cancel (reason required); closed tasks cannot be edited.

**QA flow (section 3.2)**: run it end to end and also:
- [ ] Only the QA sees the "Test" action at the QA stage; the head and Owner get "not allowed".
- [ ] "Report bugs" without text is refused; the task reopens and the developer is told; re-submit returns to QA.
- [ ] QA cannot pass without ticking "bugs solved".
- [ ] Head -> CEO/Owner -> Completed; each step notifies the right person only.
- [ ] Task with only a head, only a QA, neither; QA = assignee is skipped.

**Projects**
- [ ] Creating a project **without a deadline is impossible** (form and API); past deadline rejected; end before start rejected; the deadline cannot be cleared when editing.
- [ ] Head, QA and team members each receive an email containing the deadline and expected result; CEO/Owner are told a project was created.
- [ ] Tasks inherit the project's head and QA; with a team, an outsider cannot be assigned.
- [ ] Points: add, edit, delete, assign (becomes a task). Project cannot be completed until all done.

**Deadlines and reminders** (ask a developer to move the clock or use tasks due today/tomorrow)
- [ ] Reminders at 24 h, 2 h, due, +1/+3/+7 working days; none after completion or after a deadline change.
- [ ] Within 40 minutes after the deadline: no delay reason needed; after that, finishing requires one.
- [ ] Extension request -> manager approves/declines; original deadline still shown in history.
- [ ] Project deadline reminders (day before / day of / overdue).

**Messages and email**
- [ ] A comment reaches every person in the loop by app and email, with the full text and line breaks, not the author.
- [ ] Long comments (1500+ characters) are not cut. @mentions only offer people involved in the task.
- [ ] Mail arrives for: task created, QA needed, bugs found, completed, project created/added, comments, blockers.
- [ ] Bell: count updates within about 20 seconds without a refresh; opening it loads the latest; mark one / mark all read updates the count.

**Admin**
- [ ] Departments, employees, roles, hierarchy, working calendar and holidays, notification rules, email log, audit log.

## 6. Where to look when something is wrong
| Symptom | Check |
|---|---|
| "Cannot reach the API server" / "Unexpected token '<'" | Old website files cached or wrong address: Ctrl+F5, check the footer build line and `config.js` |
| No email | Admin -> email log (status and error); the cron job; SMTP settings |
| Reminder did not fire | Cron running every minute? Admin -> "Run a pass now" |
| Wrong person notified | Admin -> notification rules; the task's head/QA/project team |
| Something forbidden but should work | The role's permission and scope (own / team / department / company) |

## 7. Technical facts testers may need
Naive-UTC storage, company timezone Asia/Kolkata; access token 15 minutes (refreshed silently), refresh cookie 14 days; uploads up to 25 MB; API is JSON under `/api/v1` and errors look like `{"code","message","details","request_id"}` (give the `request_id` to developers).

## 8. Out of scope / by design
No timer or time sheets; no WebSocket live push (20-second polling); no marketing or sales workflow features; employees cannot create tasks; no project-deadline reminders beyond the three listed.

## 9. Reporting a bug
Include: build line from the sign-in page, account and role, steps, expected vs actual, screenshot, the Network response and its `request_id`, and the time (company timezone).
