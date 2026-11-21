# Document 10 — Final Technical Recommendation

## 1. Technology stack (with rationale and alternatives)

| Layer | Choice | Why | Alternative considered |
|---|---|---|---|
| Frontend | React 19 + TS + Vite + Tailwind + shadcn/ui + Lucide + Recharts + React Router + TanStack Query (+ React Hook Form/Zod) | Your preference; mature, great typing, huge ecosystem, shadcn gives owned, accessible components; TanStack Query removes need for Redux | Next.js (SSR unneeded for an internal SPA) |
| Backend | Python **3.12/3.13** + FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic | OpenAPI for free, strong validation, Claude writes it reliably, easy to test | Django (batteries incl. admin/auth, but you asked for FastAPI; Django would be a legitimate, lower-risk alternative for the RBAC/admin parts) |
| DB | MySQL 8.0 InnoDB | Already installed; recursive CTEs, CHECK constraints, generated columns, `SKIP LOCKED` — all used by the design | PostgreSQL (partial indexes, better JSON/RLS; not needed enough to switch) |
| Jobs | Celery + Redis 7 (+beat) | Retries, queues, scheduling; Redis in Docker (local Redis 3.0 is unsupported) | Arq/Dramatiq/APScheduler (simpler but weaker scheduling/ops) |
| Real-time | FastAPI WebSocket + Redis pub/sub, signals only | Minimal moving parts; polling fallback | SSE (simpler, one-way; also acceptable) |
| Email | SMTP via `aiosmtplib`/`smtplib` in worker, Jinja templates, Mailhog in dev | Provider-agnostic | SES/SendGrid APIs later behind same interface |
| Auth | JWT access (in-memory) + rotating refresh cookie, argon2id, token_version | Meets brief; revocable | Server sessions |
| Files | Local volume (abstracted `Storage` interface) → S3-compatible later | Cheap, simple | Direct S3 now |
| Reports | `openpyxl`/`csv` for exports, WeasyPrint/ReportLab for PDF (S) | No external service | Metabase (good for ad-hoc, separate auth problem) |
| Deploy | **Deferred** (no hosting plan). Dev: Docker Compose for Redis + Mailhog; local MySQL 8 | Keeps scope on features | — |
| Quality | pytest, hypothesis, freezegun, factory_boy, Playwright, Vitest + Testing Library, ruff, mypy, eslint, tsc, pip-audit | Enables Claude-driven development safely | — |

No microservices. No extra datastore (no Elasticsearch/Mongo). FULLTEXT in MySQL suffices for search.

## 2. Architecture
Modular monolith: React SPA → Nginx → FastAPI (REST + WS) → MySQL; Celery workers/beat via Redis; transactional **outbox** for events; central **policy layer** (RBAC + scope + state machine) shared by API, WS, jobs, exports.

## 3. Database approach
Normalized relational model; `tasks` holds current state only; **append-only history tables** for status, deadlines, delay reasons, time sessions, blocker events, audit; effective-dated reporting relationships; generated-column unique indexes to enforce "one active timer" and "one active manager"; unique keys to guarantee notification/reminder idempotency; UTC everywhere.

## 4. Development priorities
1. Permission/scope engine + hierarchy (everything depends on it).
2. Task state machine + deadline versioning (the integrity core).
3. Time tracking correctness.
4. Reminder/notification pipeline (idempotent, rule-driven).
5. Delay-reason accountability flow.
6. Blockers.
7. Reporting.
Build **tests with the rule, not after it**.

## 5. MVP scope (target ≈ 16–18 weeks realistic)
IN: auth, org/hierarchy/roles, projects (basic), tasks + assignment + state machine, employee workflow, timer, deadlines + history, overdue + mandatory delay explanation + review, in-app + email notifications with rule-based recipients, reminders/escalations, minimal blocker flow (raise/resolve), dashboards for 5 roles, 5 key reports (employee tasks, overdue, deadline extensions, time tracking, est-vs-actual) in CSV/XLSX, audit log.
OUT (v1.1+): PDF export, extension *requests* workflow, MFA (unless Owner/CEO policy forces it earlier), quiet hours/digests, holidays calendar, watchers, sub-tasks/dependencies, saved views sharing.

## 6. Future enhancements
Support/Sales/Accounts Heads (config only), SSO (Google/Microsoft), recurring tasks & templates, Slack/Teams/WhatsApp notifications, calendar sync, mobile PWA with push, task dependencies/Gantt, SLA policies per task type, custom fields, capacity planning, AI assist (summaries, risk prediction, delay-reason summarisation using Claude API — only after privacy review), multi-tenant mode.

## 7. Major technical risks & mitigations
| Risk | Likelihood/Impact | Mitigation |
|---|---|---|
| Ambiguous business rules cause rework | High / High | Close Q-list in Phase 1; ADRs; demo each phase |
| Authorization bugs (scope leaks) | Med / Critical | Central policy, matrix-driven tests, 404 for out-of-scope, security review each phase |
| Duplicate/stale reminders | Med / High | Scan-based design, UQ keys, frozen-clock tests, double-run tests |
| Timer integrity (overlaps, lost state) | Med / High | DB unique key, server timestamps, property tests |
| Employee trust / "surveillance" perception | Med / High | Transparency, no scores, self-reported time, change-management & pilot |
| AI-generated code drift/quality | Med / Med | Contract-first, CI gates, human-owned decisions, review skills, small slices |
| SMTP deliverability | Med / Med | SPF/DKIM/DMARC early, logs/retries, in-app fallback |
| Python 3.14 / dependency incompatibility | Med / Low | Pin 3.12/3.13 in Docker, lockfiles |
| Scope creep (reports/analytics) | High / Med | Fixed MVP list, change control |
| Single-server SPOF | Low / Med | Backups + restore drills, documented rebuild, move to managed DB if needed |
| Performance of recursive hierarchy/scoped reports | Low / Med | Cache scope per request, indexes, summary tables if measured |

## 8. Decisions recorded so far
Q1 one Manager · Q2 no upward assignment · Q3 no employee-created tasks · Q4 employee self-completes with assurance, review optional, Manager+ can revert (QA) · Q6 EOD = 18:30 company time · Q7/Q8 shifts 09:30–13:30 + 14:00–18:30 (8.5 productive h), Sundays and 2nd/4th Saturdays off · Q9 designed (SRS §6) · Q24 hosting out of scope.
**To confirm:** only the **company timezone**. All other questions: defaults apply.

## 9. Approval checklist (what I need from you)
- [ ] Accept or amend the 24 questions' defaults in [00-README](00-README-and-open-questions.md).
- [ ] Approve: RBAC+scope model, status model (Overdue derived, Pending dropped), one-active-timer rule, review-by-default.
- [ ] Approve stack (incl. Python 3.12/3.13 pin, sync SQLAlchemy) and MVP scope.
- [ ] Approve roadmap/timeline (26 wks full, ~16–18 wks MVP) and the Claude-driven process in doc 8 §B.
Once approved, Phase 2 starts with repo scaffolding, `CLAUDE.md`, CI and the Docker Compose dev stack — **no feature code before that sign-off.**
