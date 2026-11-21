# Document 8 — Phase-wise Roadmap & Claude-driven Delivery Method

## A. Estimating assumptions (be realistic)
- Delivery model: **Claude Code does most implementation; 1 senior human engineer (reviewer/owner of decisions) + 1 business owner** for acceptance. Estimates are *calendar working days incl. human review, rework and UAT*, not raw generation time. Typical slippage drivers: unclear rules (Q-list), email/SMTP setup, review latency, hierarchy/permission edge cases.
- Effort ranges are **ideal → realistic**; plan with the realistic number.
- Phases 2–7 are partly parallelisable (backend module then frontend slice) but the total below is sequential-safe.

| Phase | Ideal | Realistic |
|---|---|---|
| 1 Requirements & architecture (this pack + approval) | 5 d | 8 d |
| 2 Auth & organization | 10 d | 14 d |
| 3 Projects & tasks | 12 d | 17 d |
| 4 Employee workflow & time tracking | 10 d | 14 d |
| 5 Deadlines, overdue, delay reasons, escalation | 12 d | 16 d |
| 6 Notifications & automation | 12 d | 16 d |
| 7 Blockers & communication | 7 d | 10 d |
| 8 Reports & analytics | 12 d | 16 d |
| 9 Testing, security hardening, UAT *(hosting excluded)* | 8 d | 12 d |
| **Total** | **~89 d (~18 wks)** | **~125 d (~25 wks)** |
**MVP (Phases 1–6 + minimal blockers/CSV reports) ≈ 16–18 weeks realistic.** Quote **~25 weeks for full scope, hosting excluded** (Phase 2 grew by ~2 d for the work calendar; Phase 9 shrank by ~6 d without deployment). The task-level breakdown lives in [11-project-plan.md](11-project-plan.md), which supersedes the per-phase notes below where they differ.

Dependency graph: `1 → 2 → 3 → 4 → 5 → 6`; `7` needs 3 (+6 for notifications); `8` needs 4,5,7 data; `9` continuous testing, final hardening after 8. Critical path: 1→2→3→4→5→6→9.

## B. How to build this *with Claude* (process, not afterthought)

### B1. Repository set-up (done at start of Phase 2, before feature code)
1. `CLAUDE.md` at root: stack, commands (run/test/lint/migrate), architecture rules from doc 4, "never" list (no raw SQL string-building, no authorization in routers, never edit applied migrations, never touch `docs/` without being asked, never weaken `tests/permissions`).
2. `docs/` (this pack) is the **source of truth**; ADRs in `docs/adr/NNN-*.md` for every deviation.
3. `.claude/settings.json`: allow lint/test/migrate commands, deny `rm -rf`, prod credentials, git push to main; hooks: run `ruff`/`eslint`/`tsc` after edits, block commits when tests fail.
4. Slash-command/skill shortcuts: `/phase-start`, `/add-endpoint` (router+schema+service+policy+test template), `/add-migration`.
5. Pre-commit, CI (GitHub Actions or equivalent) mirrors the hooks.

### B2. Per-phase loop (repeat 9×)
1. **Plan** — Claude (Plan mode) reads the phase spec + relevant docs, outputs task breakdown + risks + open questions. Human approves.
2. **Slice** — work in **vertical slices** (migration → model → service+policy → API → tests → UI → e2e) of ≤ 1 day each, one PR per slice.
3. **Test-first for rules** — state machine, permissions, reminders, timers get tests *before* implementation.
4. **Implement** — Claude Code; independent sub-agents in parallel for backend vs frontend once the OpenAPI contract is fixed.
5. **Verify** — run tests/lint/types; start the app and exercise the feature (the `run` skill / browser) — not just unit tests.
6. **Review** — `/code-review` (correctness) + `/security-review` on the branch; `/simplify` pass; human reviews migrations, permissions, notification rules personally.
7. **Gate** — acceptance checklist signed by business owner; demo; update docs/ADRs; tag release.

### B3. Guard-rails specific to AI-generated code
- **Human-owned decisions**: schema changes, permission matrix, state machine, retention, anything in Q-list.
- Contract-first: OpenAPI generated TS client → compile errors reveal drift.
- Golden tests: permission matrix YAML, status-transition table, reminder timeline fixtures with a frozen clock (`freezegun`/injectable `Clock`).
- Property tests (hypothesis) on timers: random start/pause/stop sequences never yield overlaps or negative durations.
- Seed + factory data (`factory_boy`) so Claude can reproduce scenarios; a `make demo-data` command with the sample org (Owner, CEO, Manager, 3 heads, ABC the AI/ML dev, Support/Sales/Accounts staff).
- Dependency policy: Claude may not add libraries without listing them in the PR description; versions pinned.
- Prompts reference requirement IDs (e.g., "implement FR-050..054") so traceability is kept; PR template lists FR/NFR IDs covered; a traceability table lives in `docs/traceability.md`.
- Secrets never in prompts; prod access never granted to the agent.
- Context hygiene: one phase per session/branch, summaries in `docs/progress.md` at the end of each session.

## C. Phases

### Phase 1 — Requirements & architecture (this deliverable)
- **Objectives:** agree scope, rules, hierarchy, permission model, DB, stack. **Tasks:** answer Q1–Q24, approve docs, pick Python 3.12/3.13, set up repo skeleton decisions, UX wireframes for the 6 critical screens (dashboard, create task, task detail, employee day, delay form, blocker form), seed org chart. **Dep:** none. **Accept:** signed-off docs; Q-list closed or defaults accepted; clickable wireframes approved. **Effort:** 5–8 d.

### Phase 2 — Authentication & organization
- **Features:** login/refresh/logout/reset, lockout, rate limit, roles/permissions/scopes, user & employee CRUD, departments, reporting hierarchy (effective-dated, cycle-safe), seed data, `/auth/me`, app shell + role-aware navigation, hierarchy tree, audit-log foundation.
- **Backend:** core (config, db, errors, clock, logging), auth module, rbac policy engine + scope resolver, org module, activity_log writer. **Frontend:** Vite/React skeleton, auth flows, layout/sidebar, permission-aware routing, employee/department/hierarchy/role screens, generated API client. **DB:** users, refresh_tokens, password_reset_tokens, roles, permissions, role_permissions, user_roles, departments, employees, reporting_relationships, manager_departments, activity_logs, system_settings. **API:** auth, employees, departments, hierarchy, roles, permissions, users/roles, settings.
- **Dependencies:** Phase 1. **Accept:** permission-matrix test suite green for org features; manager sees only subtree; dept head only department; hierarchy change preserves history; refresh-reuse detection works; no hardcoded dept names. **Testing:** unit (policy, scope CTE, cycle detection), API authz matrix, auth security tests, FE component tests. **Effort:** 10–14 d.

### Phase 3 — Projects & tasks
- **Features:** projects, task CRUD, assignment (scope+rank validation), list/filter/sort/saved views, task detail shell, priority management, state machine skeleton + status history, categories/types, attachments (secure upload).
- **Backend:** projects, tasks, assignments, state machine, files module. **Frontend:** create-task form with workload/conflict panel, task list (table/board), task detail, project screens. **DB:** projects, project_members, task_categories/types, tasks, task_assignments, task_status_history, task_attachments. **API:** projects, tasks CRUD, reassign, priority, attachments, timeline.
- **Dep:** 2. **Accept:** Owner→ABC task created per sample; Manager cannot assign outside T; invalid transitions → 409; employee cannot see others' tasks; attachments validated & authorized. **Testing:** state-machine table tests, IDOR tests, upload abuse tests, list performance on 50k seeded tasks. **Effort:** 12–17 d.

### Phase 4 — Employee workflow & time tracking
- **Features:** My Day dashboard, acknowledge, start/pause/resume/stop with server-side sessions, switch-timer, progress updates, submit-for-review/complete with guards, review approve/reject, task history, auto-stop of forgotten timers (job stub), manual time requests/approval.
- **Backend:** timetracking module, updates, review. **Frontend:** timer widget (hydrates from server), My Tasks, submit dialog, time screens. **DB:** task_time_logs (+generated unique key), task_time_corrections, task_updates. **API:** time/*, progress, submit, review.
- **Dep:** 3. **Accept:** refresh/close browser keeps timer; second device can't start parallel timer (409); overlap rejected; sample 3-session example sums to 9 h; every correction audited. **Testing:** concurrency tests (parallel starts), property tests on sessions, E2E (Playwright) of employee day. **Effort:** 10–14 d.

### Phase 5 — Deadlines, overdue, delay reasons, escalation
- **Features:** deadline edit/history/version, extension requests (S), overdue derivation + flag, mandatory delay explanation gate, review decisions, escalation records, extension statistics.
- **Backend:** deadlines, delays modules; overdue computation in scanner (job wiring completed in P6, logic + tests here with injected clock). **Frontend:** deadline card & dialog, overdue queue, delay form/gate, review screens. **DB:** task_deadline_history, deadline_extension_requests, task_delay_reasons, task_delay_reviews. **API:** deadline, delay-reasons, review, delays/pending.
- **Dep:** 4. **Accept:** 3 extensions show original + current + count + actors + reasons; original never changes (DB test); explanation cannot be edited/deleted; accept ≠ complete; employee can't dismiss gate. **Testing:** timeline fixtures (frozen clock), authorization, DB-privilege tests. **Effort:** 12–16 d.

### Phase 6 — Notifications & automation
- **Features:** outbox + relay, rule-based recipient resolver, dedupe, in-app center, WebSocket, email templates/logs/retry, reminder rules + scanner + reminder_log, escalation, preferences, daily digest (S), admin views for rules/failed emails/jobs.
- **Backend:** notifications, reminders, Celery app/beat/queues, SMTP, WS gateway. **Frontend:** bell, center, preferences, admin rules UI. **DB:** outbox_events, notification_rules, notification_preferences, notifications, email_logs, reminder_rules, reminder_log. **API:** notifications, admin rules/email logs, ws ticket.
- **Dep:** 3 (events), 5 (deadline version), infra (Redis/Mailhog in Docker). **Accept:** Owner-assigns-ABC reaches ABC, Manager, Dev Head, CEO exactly once each; runs-twice job sends nothing new; deadline change after reminder ⇒ new schedule, old never fires; completed/cancelled stop reminders; SMTP outage ⇒ retries then `failed`, in-app unaffected. **Testing:** frozen-clock reminder matrix, duplicate-run tests, Mailhog integration, WS tests, load test 200 users. **Effort:** 12–16 d.

### Phase 7 — Blockers & communication
- **Features:** comments/questions/mentions, blocker lifecycle, auto Blocked/timer pause, blocked-time accounting, manager actions, attachments in context.
- **DB:** task_comments, comment_mentions, task_blockers, task_blocker_events. **API:** comments, blockers/*. **Frontend:** discussion tab, blocker form & queue.
- **Dep:** 3, 4, 6. **Accept:** blocker pauses timer & excludes time; resolve restores previous status; history complete; notifications per rules. **Testing:** state interplay tests (blocker × hold × overdue), XSS tests. **Effort:** 7–10 d.

### Phase 8 — Reports & analytics
- **Features:** 12 reports, dashboards finalised for 5 roles, CSV/XLSX export (PDF S), async export jobs, workload indicator, formula-injection-safe exports.
- **Backend:** reports module (read-optimised queries; summary views/tables if needed), exports job. **Frontend:** Recharts dashboards, filter bar, saved views. **DB:** indexes tuned via EXPLAIN; optional `daily_task_snapshots`. **API:** dashboards/*, reports/*, exports.
- **Dep:** 4, 5, 7. **Accept:** numbers reconcile to raw logs (reconciliation test); scope respected in every report; completion/on-time/active/elapsed shown separately; export opens cleanly in Excel. **Testing:** golden dataset comparisons, scope tests, performance (<1.5 s). **Effort:** 12–16 d.

### Phase 9 — Testing & hardening (hosting/deployment deferred)
- **Features:** full regression, security testing (OWASP ASVS checklist, authz fuzz, dependency audit), performance test on seeded data, user training material, UAT with real data in a local/staging-like environment. **Not included:** Nginx/TLS, production Compose, backups, monitoring, go-live (future "Hosting" phase, unplanned).
- **Dep:** all. **Accept:** zero open high/critical issues; permission matrix 100% covered; UAT sign-off. **Effort:** 8–12 d.

## D. Milestones & demos
M1 (end P2) login + org · M2 (end P3) create/assign tasks · M3 (end P4) employee works & tracks time · M4 (end P5) deadline accountability · **M5 (end P6) = MVP internal pilot with one department (Developers)** · M6 (end P7) blockers · M7 (end P8) reporting · M8 (end P9) UAT sign-off, release-candidate build (go-live/hosting deferred).
Pilot first (Developers + Manager) for 2 weeks before company-wide rollout.
