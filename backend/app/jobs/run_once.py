"""Run the background jobs once and exit. This is what the cPanel cron job calls, every minute:

    /home/USERNAME/virtualenv/DOMAIN/3.12/bin/python /home/USERNAME/DOMAIN/app/jobs/run_once.py >> /home/USERNAME/DOMAIN/logs/cron.log 2>&1

One run = reminder scan, event -> notification relay, email sending/retries (and the forgotten-timer guard when enabled).
Only one run works at a time (database named lock); a run that finds another one busy exits at once with code 0.
Exit code: 0 = finished or skipped because another run is busy, 1 = a database/configuration error (see the log).

Optional: `--duration 50 --interval 10` keeps working for 50 seconds, one pass every 10 s (faster notification mail, still
exits before the next cron start). `--check` only prints the database version and exits."""

import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the folder that contains `app/`
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

log = logging.getLogger("tms.cron")


def _setup_logging(log_file: str) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in [h for h in root.handlers if getattr(h, "_tms_cron", False)]:  # calling main() twice must not double the lines
        root.removeHandler(h)
    out = logging.StreamHandler(sys.stdout)
    out._tms_cron = True  # type: ignore[attr-defined]
    out.setFormatter(fmt)
    root.addHandler(out)
    try:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf8")
        fh._tms_cron = True  # type: ignore[attr-defined]
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as exc:  # an unwritable log folder must never stop the jobs
        log.warning("cannot write the log file %s: %s", log_file, exc)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the TMS background jobs once (for cron).")
    ap.add_argument("--log-file", default=str(ROOT / "logs" / "scheduler.log"))
    ap.add_argument("--duration", type=int, default=0, help="keep running passes for this many seconds (default: a single pass)")
    ap.add_argument("--interval", type=int, default=10, help="seconds between passes when --duration is used")
    ap.add_argument("--check", action="store_true", help="print the database version and exit")
    args = ap.parse_args(argv)
    _setup_logging(args.log_file)

    engine = None
    try:
        from sqlalchemy import text

        import app.models_registry  # noqa: F401  (registers every model)
        from app.core.db import SessionLocal, engine
        from app.jobs.scheduler import run_locked

        with SessionLocal() as db:
            version = db.execute(text("SELECT VERSION()")).scalar()
        log.info("database server version: %s", version)
        if args.check:
            return 0

        started = time.monotonic()
        last_scan = float("-inf")
        passes = 0
        while True:
            scan = time.monotonic() - last_scan >= 60  # the reminder scan runs at most once a minute
            result = run_locked(SessionLocal, scan=scan)
            if result is None:
                return 0  # another run is working; it will do everything
            if scan:
                last_scan = time.monotonic()
            passes += 1
            log.info("pass %d done: %s", passes, {k: v for k, v in result.items()})
            if time.monotonic() - started + args.interval >= args.duration:
                return 0
            time.sleep(args.interval)
    except Exception:  # noqa: BLE001
        log.exception("scheduler run failed")
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        logging.shutdown()


if __name__ == "__main__":
    sys.exit(main())
