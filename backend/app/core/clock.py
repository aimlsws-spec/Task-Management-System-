"""Single source of 'now'. All stored timestamps are naive UTC. Tests can freeze the clock."""

from collections.abc import Callable
from datetime import UTC, datetime

_override: Callable[[], datetime] | None = None


def utcnow() -> datetime:
    if _override is not None:
        return _override()
    return datetime.now(UTC).replace(tzinfo=None)


def freeze(moment: datetime | None) -> None:
    """Freeze the clock at `moment` (naive UTC); pass None to unfreeze."""
    global _override
    _override = None if moment is None else (lambda: moment)
