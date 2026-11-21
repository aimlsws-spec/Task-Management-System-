"""The timer under stress: random sequences keep the invariants, and two simultaneous starts never both win."""

import threading
from datetime import timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select

from app.core import clock
from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.org.models import Employee
from app.modules.rbac.policy import Principal, effective_permissions
from app.modules.tasks.models import Task
from app.modules.timetracking import queries as q
from app.modules.timetracking import service as ts
from app.modules.timetracking.models import TimeLog

from .helpers import BASE, make


def principal(db, email="abc@demo.example.com") -> Principal:
    user = db.scalar(select(User).where(User.email == email))
    emp = db.scalar(select(Employee).where(Employee.user_id == user.id))
    perms, roles, rank = effective_permissions(db, user.id)
    return Principal(db=db, user=user, employee=emp, permissions=perms, roles=roles, rank=rank)


def check_invariants(seeded, emp_id: int) -> None:
    with seeded() as s:
        logs = s.scalars(select(TimeLog).where(TimeLog.employee_id == emp_id).order_by(TimeLog.started_at, TimeLog.id)).all()
        assert sum(1 for lg in logs if lg.ended_at is None) <= 1, "two timers open at once"
        closed = [lg for lg in logs if lg.ended_at is not None]
        for lg in closed:
            assert lg.duration_seconds == int((lg.ended_at - lg.started_at).total_seconds()) >= 0
        for a, b in zip(logs, logs[1:], strict=False):
            assert a.ended_at is None or a.ended_at <= b.started_at, f"sessions overlap: {a.id} / {b.id}"
        per_task: dict[int, int] = {}
        for lg in closed:
            per_task[lg.task_id] = per_task.get(lg.task_id, 0) + lg.duration_seconds
        now = clock.utcnow()
        m = q.active_seconds_map(s, list({lg.task_id for lg in logs}), now)
        for tid, total in per_task.items():
            assert m[tid] >= total  # the map equals closed time plus anything still running


op_start = st.tuples(st.just("start"), st.integers(0, 1), st.booleans())
op_stop = st.tuples(st.just("stop"), st.integers(0, 1), st.sampled_from(["paused", "stopped"]))
op_wait = st.tuples(st.just("wait"), st.integers(1, 240), st.just(None))
clock_state = {"t": 0}


@settings(max_examples=12, deadline=None, suppress_health_check=list(HealthCheck))
@given(st.lists(st.one_of(op_start, op_stop, op_wait), min_size=1, max_size=18))
def test_random_timer_sequences_never_break_the_rules(seeded, client, as_user, ops):
    if "tasks" not in clock_state:
        clock.freeze(BASE)
        clock_state["tasks"] = [make(client, as_user, seeded, title=f"Property task {i}")["id"] for i in range(2)]
    tasks = clock_state["tasks"]
    with seeded() as s:  # every example starts with nothing running, and time only ever moves forward
        for lg in s.scalars(select(TimeLog).where(TimeLog.ended_at.is_(None))):
            clock.freeze(BASE + timedelta(minutes=clock_state["t"]))
            q.close(s, lg, clock.utcnow(), "stopped")
        s.commit()
    emp_id = None
    for kind, a, b in ops:
        if kind == "wait":
            clock_state["t"] += a
            clock.freeze(BASE + timedelta(minutes=clock_state["t"]))
            continue
        clock.freeze(BASE + timedelta(minutes=clock_state["t"]))
        with seeded() as s:
            p = principal(s)
            emp_id = p.employee.id
            task = s.get(Task, tasks[a])
            running = q.open_session(s, emp_id)
            if running is not None and q.cap_for(s, running) <= clock.utcnow():
                running = None  # the cap will close it on contact
            try:
                if kind == "start":
                    ts.start_timer(s, p, task, b, None)
                    assert b or running is None, "a second timer was allowed without switching"
                else:
                    ts.stop_timer(s, p, task, b, None)
                    assert running is not None and running.task_id == task.id
                s.commit()
            except AppError as e:
                s.rollback()
                assert e.status in (409,), e.code  # only the expected refusals, never a crash
                if kind == "start":
                    assert running is not None and (not b or running.task_id == task.id)
                else:
                    assert running is None or running.task_id != task.id
        check_invariants(seeded, emp_id)
    clock_state["t"] += 1


def test_two_simultaneous_starts_only_one_wins(client, as_user, seeded):
    clock.freeze(BASE)
    ids = [make(client, as_user, seeded, title=f"Race {i}")["id"] for i in range(2)]
    for round_no in range(6):
        outcomes: list[str] = []
        gate = threading.Barrier(2)

        def attempt(tid: int, gate=gate, outcomes=outcomes):
            with seeded() as s:
                p = principal(s)
                task = s.get(Task, tid)
                gate.wait()
                try:
                    ts.start_timer(s, p, task, False, None)
                    s.commit()
                    outcomes.append("started")
                except AppError as e:
                    s.rollback()
                    outcomes.append(e.code)

        threads = [threading.Thread(target=attempt, args=(tid,)) for tid in ids]
        [t.start() for t in threads]
        [t.join(timeout=30) for t in threads]
        assert sorted(outcomes) == ["TIMER_ALREADY_ACTIVE", "started"], f"round {round_no}: {outcomes}"
        with seeded() as s:
            open_logs = s.scalars(select(TimeLog).where(TimeLog.ended_at.is_(None))).all()
            assert len(open_logs) == 1
            q.close(s, open_logs[0], clock.utcnow(), "stopped")
            s.commit()
