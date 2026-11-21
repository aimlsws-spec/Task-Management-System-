# ADR 006: QA in the loop, optional head per task, date-only deadlines, mail to the whole loop

Status: accepted. Extends ADR 003 (review chain) and ADR 004 (deadlines only).

## Decisions
1. **Deadlines are dates.** `due_time` / `expected_time` are removed from every API schema and screen. A deadline falls at the end
   of that working day (EOD, 18:30 company time, `workcal`). A client that still sends `due_time` gets 422.
2. **Head and QA are optional, per project and per task.** `projects.qa_employee_id`, `tasks.head_employee_id`, `tasks.qa_employee_id`
   (migration 0011). A task's effective head/QA is its own, else its project's (`tasks/loop.py`). No head, no QA and no project = one
   employee's own work, completed directly as before.
3. **Review chain** for any task with a project, head or QA: assignee finishes -> `qa` -> `head` -> `leadership` (CEO or Owner) -> Completed.
   A stage is skipped when nobody holds it, and nobody reviews their own work. At the QA stage "reject" is the bug report (reason
   `qa_defect`, found by QA): the task is Reopened, the assignee fixes it and submits again, and it returns to QA (full re-test).
   QA passing it ("all bugs solved") moves it to the head. Removing a QA/head moves waiting work to the next stage.
4. **Everybody in the loop gets every message.** New selectors `TASK_QA` and `TASK_LOOP` (assignee, assigner, task head/QA, project head,
   QA, team and creator). Comments, questions, replies, blocker raised/replied/resolved, bugs found and final completion go to the whole
   loop by app notification **and email**, immediately (not held for working hours), with the full text (no 300-character cut), the
   project, task status and the people involved. Rules version 4: run `python -m app.cli seed-core` after upgrading an existing database
   to add the new rules (existing Admin edits are not touched).

## Not changed
`rbac/seed.py` and the permission matrix are untouched: QA and heads act through the object rule "it is your turn", not a new permission.
