from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit.models import SystemSetting

DEFAULT_KEYS = {
    "company_timezone": lambda: get_settings().company_timezone,
    "eod_time": lambda: get_settings().eod_time,
    "delay_stale_days": lambda: 3,  # an overdue explanation older than this, with no news, must be refreshed
    "timer_max_session_hours": lambda: 10,  # hard cap on one continuous session
    "timer_checkin_hours": lambda: [4, 8],
    "timer_checkin_clock": lambda: "19:00",
    "timer_hard_cutoff_clock": lambda: "22:00",
}


def get_setting(db: Session, key: str):
    row = db.get(SystemSetting, key)
    if row is not None and row.value is not None:
        return row.value
    return DEFAULT_KEYS[key]()


def set_setting(db: Session, key: str, value, user_id: int | None = None) -> None:
    if key not in DEFAULT_KEYS:
        raise KeyError(key)
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=value, updated_by=user_id))
    else:
        row.value = value
        row.updated_by = user_id
    db.flush()  # autoflush is off; make the new value visible to subsequent reads in this transaction
