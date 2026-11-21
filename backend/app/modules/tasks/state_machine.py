"""Table-driven task status machine (SRS section 3). Invalid moves are rejected with 409 INVALID_TRANSITION.

Phase 3 wires: acknowledge, cancel and reassign. The remaining edges (start/hold/blocked/complete/review/
revert/reopen) are defined here already so Phases 4-7 plug in without changing the rules."""

from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import Conflict
from app.modules.tasks.models import OPEN_STATUSES, Task, TaskStatusHistory

# (from, to) -> who may perform it: 'assignee', 'manager' (authorized management), 'system'
TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("assigned", "acknowledged"): {"assignee"},
    ("reopened", "acknowledged"): {"assignee"},
    ("assigned", "in_progress"): {"assignee"},
    ("acknowledged", "in_progress"): {"assignee"},
    ("reopened", "in_progress"): {"assignee"},
    ("in_progress", "on_hold"): {"assignee", "manager"},
    ("on_hold", "in_progress"): {"assignee", "manager"},
    ("in_progress", "blocked"): {"assignee", "system"},
    ("blocked", "in_progress"): {"assignee", "system"},
    ("in_progress", "under_review"): {"assignee"},
    ("in_progress", "completed"): {"assignee"},  # only when the task does not require review (Phase 4 guard)
    ("under_review", "completed"): {"manager"},
    ("under_review", "reopened"): {"manager"},
    ("completed", "reopened"): {"manager"},  # "Revert"
    ("cancelled", "assigned"): {"manager"},  # restore (Owner/CEO)
    **{(s, "cancelled"): {"manager"} for s in OPEN_STATUSES},
}


def can_transition(frm: str, to: str, actor: str) -> bool:
    return actor in TRANSITIONS.get((frm, to), set())


def transition(db: Session, task: Task, to: str, user_id: int | None, actor: str, reason: str | None = None) -> None:
    if not can_transition(task.status, to, actor):
        raise Conflict("INVALID_TRANSITION", f"A {task.status.replace('_', ' ')} task cannot move to {to.replace('_', ' ')}")
    force_status(db, task, to, user_id, reason)


def force_status(db: Session, task: Task, to: str, user_id: int | None, reason: str | None = None) -> None:
    """Record a status change without the edge check (used by reassign, which resets an open task to 'assigned')."""
    db.add(
        TaskStatusHistory(task_id=task.id, from_status=task.status, to_status=to, changed_by_user_id=user_id,
                          reason=reason, created_at=clock.utcnow())  # fmt: skip
    )
    task.status = to
    task.version += 1
