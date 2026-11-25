"""Process notifications and email right after a change (ADR 007). Runs after the HTTP response was sent, takes the same named
lock as the cron job (so the two never overlap) and never raises. The reminder scan is throttled to once a minute per worker."""

import logging
import time

log = logging.getLogger("tms.kick")
_last_scan = float("-inf")


def should_scan() -> bool:
    return time.monotonic() - _last_scan >= 60


def kick() -> None:
    global _last_scan
    try:
        from app.core.db import SessionLocal
        from app.jobs.scheduler import run_locked

        scan = time.monotonic() - _last_scan >= 60
        result = run_locked(SessionLocal, scan=scan)
        if scan and result is not None:
            _last_scan = time.monotonic()
    except Exception:  # noqa: BLE001 - the change itself already succeeded; cron will pick the work up
        log.exception("post-request job pass failed")
