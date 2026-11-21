# ADR 005: run on cPanel shared hosting (Passenger + cron, no WebSocket)

Status: accepted. Requested by the deployer. Supersedes the in-process scheduler and WebSocket parts of ADR 001.

## Decision
* **Passenger/WSGI.** `passenger_wsgi.py` wraps the FastAPI app with `a2wsgi.ASGIMiddleware`. The app has no ASGI lifespan and
  starts no threads.
* **Cron instead of an in-process scheduler.** `app/jobs/run_once.py` runs one pass (`scheduler.tick`) and exits; cPanel cron
  starts it every minute. The `Scheduler` thread class and `TMS_INLINE_JOBS` were removed.
* **One pass at a time, on any MySQL/MariaDB.** `scheduler.run_locked` takes a named lock (`GET_LOCK`, name includes the
  database) on its own connection. The Admin "run now" button uses the same function (409 when busy). The server frees the
  lock when the connection ends, so a killed run cannot lock the jobs. Because only one pass runs at a time,
  `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8 / MariaDB 10.6+ only) was replaced by a plain `FOR UPDATE`. Duplicates stay
  impossible: `(user, dedupe_key)` unique key for notifications, status flips on outbox events and emails, and each email
  is committed right after it is handled (a killed run can repeat at most the one email that was in flight).
* **No WebSocket.** `/ws`, `/ws/ticket` and `core/realtime.py` were removed. The bell polls `GET /notifications/unread-count`
  every 20 s (one query, paused in hidden tabs, stopped on 401/logout), loads `GET /notifications` when opened, and every
  successful mutation re-reads the count.
* `TMS_FRONTEND_DIR` (optional) lets the API answer page URLs with `index.html` where only the API runs through Passenger.
* The Admin status shows whether cron is running (a pass within 3 minutes) instead of an "inline jobs" flag.

## Consequences
* Notification/email latency is up to one cron interval (`--duration 50 --interval 10` shortens it).
* Alembic migrations and the schema were not changed. Tests run on MySQL 8 only; the shipped SQL dump has the MySQL-8-only
  collation replaced by `utf8mb4_unicode_ci` and no `CREATE DATABASE`, so it imports on MySQL 5.7+ (not yet tried on 5.7 here).
