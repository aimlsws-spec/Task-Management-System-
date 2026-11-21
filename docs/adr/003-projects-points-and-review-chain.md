# ADR 003: Projects with expected results, later-added points, a project head and a review chain

**Status:** accepted (2026-11-17). Extends the Phase 3 "project" (a plain label on a task). No permission-matrix change.

## Context
The Owner or CEO starts a project (for example *Elala*) with the tasks they know and the result they expect, and remembers
more things later. Some projects have a head, who must be kept in the loop and who approves finished work before it reaches
leadership. Without a head, work is assigned straight to an employee.

## Decisions
1. **Project** = name, description, **expected result**, optional **head** (any active employee), a **team** (members) and an
   ordered list of **points**. Created by anyone with `project.manage` (Owner, CEO, Manager, Department Head today).
2. **Points** are planned work that is not yet a task. Points can be added, edited and removed (while unassigned) at any time.
   **Assigning** a point creates a normal task in the project (so every existing rule applies: deadline, priority, scope, rank,
   notifications) and links it. A task can also be created straight into a project with no point (the "no head, assign
   directly" case). When the project has a team, assignees must be on it (the head counts); with no team anyone in the
   assigner's scope may be chosen.
3. **Head in the loop.** The head is told when a task is created in the project, when work needs their approval and when the
   project is completed. The head can see every task of the project even outside their normal scope.
4. **Review chain, project tasks only.** When the assignee marks a project task done it becomes *Under review* with a
   `review_stage`:
   `head` (project has a head who is not the assignee) -> the head approves -> `leadership` -> **CEO or Owner** (either one)
   marks it reviewed -> *Completed*. With no head the task goes straight to `leadership`. Either reviewer can send it back
   (task becomes *Reopened*, stage cleared). Only the project head can act at stage `head`; only the Owner or CEO at `leadership`.
   Tasks outside a project keep the existing flow (complete, or optional single-step review).
5. **Project completion.** A project is *ready for review* when it has no unassigned points and every task is completed or
   cancelled (and there is at least one task). Owner and CEO are told; either one marks the **project completed**. Adding a
   new point to a completed project reopens it. Only Owner/CEO may complete a project (a role check, not a new permission).
6. **Emails.** All new notices use the existing rule table (editable by the Admin) and are never held for working hours.
   Emails carry absolute links built from `TMS_APP_BASE_URL`; the Admin page warns while it still points at localhost.

## Consequences
* New tables `project_points`, `project_members`; new columns on `projects` and `tasks.review_stage` (migration 0010).
* "Waiting for your review" is now computed per person (`awaiting_my_review`): the head sees stage `head`, Owner/CEO see stage
  `leadership`.
* Not built: percentage weighting of points, sub-projects, per-project permissions beyond head/team.
