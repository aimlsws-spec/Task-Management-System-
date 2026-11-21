# ADR 001: Background jobs run from MySQL, not Celery and Redis

**Status:** accepted (Phase 6, 2026-11-16). Supersedes the Celery + Redis choice in docs 04 and 10.

## Context
Phase 6 needs reliable notifications, reminders, escalations, email retries and the forgotten-timer guard.
The original plan used Celery with Redis. On the build machine there is no running Docker and the installed Redis
(3.0.504) is too old for Celery. The system is MySQL-only by decision, and hosting is out of scope.

## Decision
Everything is stored in MySQL and driven by a scheduler thread inside the API process:

* **Transactional outbox.** Every audited task action also writes an `outbox_events` row in the *same transaction*.
  A rolled-back action leaves no event; a committed one cannot be lost.
* **Relay.** Turns events into notifications and queued emails using database rules (`notification_rules`), with
  `SKIP LOCKED` and unique keys, so running twice or in parallel never duplicates anything.
* **Scan, don't schedule.** Reminders are found by scanning tasks as they are now; exactly-once comes from a unique
  `reminder_log` row (task + rule + deadline version + assignee). Nothing has to be cancelled when a deadline moves.
* **Single scheduler.** A MySQL named lock (`GET_LOCK`) lets only one process run it, so several API processes are safe.
* **Email.** `email_logs` with retry/backoff (1 min, 5 min, 30 min, 2 h, 12 h), a working-hours window for routine
  mail, urgent mail exempt, and stale reminders dropped at send time.
* **Real time.** WebSocket "signals" with single-use tickets; the page re-reads data over the normal API. The bell also
  polls every 30 s, so nothing depends on a push arriving.

## Consequences
* No extra services to run or secure; jobs survive restarts; the whole thing is testable with a frozen clock.
* The WebSocket push only reaches tabs connected to the process that runs the scheduler. Other processes' tabs use
  the polling fallback. If push must span processes later, add a Redis pub/sub bridge behind `core/realtime.py`.
* Throughput is bounded by one scheduler thread: ample for hundreds of users and thousands of events per day.
  If it is ever outgrown, `jobs/scheduler.py:tick` can be called from Celery or another runner unchanged.
