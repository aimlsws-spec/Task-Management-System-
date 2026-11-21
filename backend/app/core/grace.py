"""The grace period: a task is not "late" until this long after its deadline (default 40 minutes).
Every place that decides overdue / late / explanation-required goes through here, so they always agree."""

from datetime import datetime, timedelta

from app.core.config import get_settings


def grace() -> timedelta:
    return timedelta(minutes=max(0, get_settings().overdue_grace_minutes))


def late_cutoff(now: datetime) -> datetime:
    """A task is late when its deadline is earlier than this."""
    return now - grace()


def late_after(due_at: datetime) -> datetime:
    """The moment a task with this deadline becomes late."""
    return due_at + grace()
