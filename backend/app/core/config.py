from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # absolute path to backend/.env: cron and Passenger start in other folders
    model_config = SettingsConfigDict(env_file=str(Path(__file__).resolve().parents[2] / ".env"), env_prefix="TMS_", extra="ignore")

    env: str = "dev"
    # REQUIRED, MySQL 8 only: mysql+pymysql://user:pass@localhost:3306/tms?charset=utf8mb4
    database_url: str
    secret_key: str = "dev-only-change-me-dev-only-change-me-32b"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    reset_token_minutes: int = 30
    cookie_secure: bool = False
    # DEV/TESTING ONLY: keep each browser tab's session separate (refresh token handed to the tab and kept in
    # sessionStorage) so several roles can be logged in at once. Ignored unless env == "dev".
    dev_multi_session: bool = False
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    login_rate_limit_per_minute: int = 10
    # Company calendar defaults (overridable via system_settings)
    company_timezone: str = "Asia/Kolkata"
    eod_time: str = "18:30"
    cors_origins: str = "http://localhost:5173"
    # --- email. 'log' writes emails to the log (dev default); 'smtp' really sends them.
    email_backend: str = "log"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none
    email_from: str = "SeaWind Tasks <no-reply@localhost>"
    app_base_url: str = "http://localhost:5173"  # used for links inside emails
    # Background jobs (outbox relay, reminders, email) are NEVER started inside the API: the cPanel cron job runs
    # `python app/jobs/run_once.py` every minute. (An old TMS_INLINE_JOBS line in .env is simply ignored.)
    # Folder holding the compiled website (index.html). When set, the API answers page URLs such as /tasks/5 with index.html
    # so a browser refresh works on hosting where only the API runs through Passenger. Leave empty when nginx/Apache does it.
    frontend_dir: str = ""
    # ADR 007: after a successful change (create task/project, comment, ...) process notifications and email right away, in the
    # same worker AFTER the response was sent, so mail does not depend on the cron job being set up. Cron stays the safety net
    # and the only thing that is guaranteed to run reminders when nobody is using the site. Off by default (tests, dev).
    mail_after_request: bool = False
    # ADR 008: every sign-in (and sign-up) needs a one-time code mailed to the person's registered address. Switch off only as an
    # emergency measure when mail cannot be delivered; the Admin can then still get in.
    otp_enabled: bool = True
    # A database that is behind this version of the app upgrades itself (alembic upgrade head) the first time the API is used, under a
    # named MySQL lock so two workers never migrate at once. Migrations here are additive. Set false to upgrade by hand.
    auto_migrate: bool = True
    otp_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_seconds: int = 30
    otp_max_sends: int = 5
    # The product runs on deadlines only. The timer engine stays in the code (and its tests) behind this switch.
    time_tracking: bool = False
    # A task is not late until this many minutes after its deadline (then an employee must give a reason)
    overdue_grace_minutes: int = 40
    upload_dir: str = "uploads"  # relative paths resolve against the backend folder
    max_upload_mb: int = 25


@lru_cache
def get_settings() -> Settings:
    return Settings()
