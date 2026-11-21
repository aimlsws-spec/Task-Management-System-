# ADR 004: Deadlines only: no timer, no effort estimates, no Time page

**Status:** accepted (2026-11-17). Supersedes the Phase 4 timer as a product feature (the engine stays behind a switch).

## Decision
The company manages work by **deadline**, not by hours. So the product no longer shows or asks for:
* an effort estimate when creating a task or assigning a project point (the API keeps an optional `estimated_hours`, default 8, only so workload maths stays defined);
* a timer: no timer bar, no Start/Pause/Stop, no "Timer running", no session list, no "Add missing time", no forgotten-timer check-ins or auto-stop alerts;
* the **Time page** and its menu entry; the "tracked time or explain why" rule when completing a task; the Effort card on a task.

"Start work" now only moves a task to *In progress* (the assigner is still told on the first start).

## How
`TMS_TIME_TRACKING` (default `false`) gates the timer engine: start does not open a session, pause/stop answer `TIMER_DISABLED`,
`/time/active` is empty, the completion rule is skipped and the scheduler does not run the forgotten-timer guard. The old code and its
~200 tests remain; the test suite sets the switch on, and `tests/test_no_timer.py` covers the off mode. Setting the switch to `true`
brings the engine back (the screens that were removed would have to be restored from git history).

## Consequences
Reports or workload screens that mention hours show numbers based on the default estimate and are not meaningful; remove or rework them if they matter.
