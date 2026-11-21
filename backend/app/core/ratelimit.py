"""Tiny in-process sliding-window limiter (dev/single-instance). Swap for Redis in Phase 6."""

import time
from collections import defaultdict, deque

from app.core.errors import AppError

_hits: dict[str, deque[float]] = defaultdict(deque)


def check(key: str, limit: int, window_seconds: int = 60) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window_seconds:
        q.popleft()
    if len(q) >= limit:
        raise AppError("RATE_LIMITED", "Too many requests, try again shortly", 429)
    q.append(now)


def reset() -> None:
    _hits.clear()
