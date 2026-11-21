"""Default notification and reminder rules. Seeded once per event type; afterwards the Admin owns them
(enable/disable, channels, mandatory), so re-running the seeder never overwrites a change."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.notifications.models import NotificationRule, ReminderRule

IN, EM, BOTH = "in_app", "email", "in_app,email"
# (event, selector, channels, mandatory, urgent, enabled, condition)
_R: list[tuple] = []


def r(event, selector, channels=BOTH, mandatory=False, urgent=False, enabled=True, cond=None):
    _R.append((event, selector, channels, mandatory, urgent, enabled, cond))


# --- new task: the assignee, their line manager, department head, the Manager above them; the CEO when the Owner assigns
r("TASK_CREATED", "ASSIGNEE", mandatory=True)
r("TASK_CREATED", "DIRECT_MANAGER")
r("TASK_CREATED", "DEPARTMENT_HEAD")
r("TASK_CREATED", "ANCESTOR_ROLE:manager")
r("TASK_CREATED", "ROLE:ceo", cond={"assigner_role": ["owner"]})
r("TASK_CREATED", "ROLE:ceo", IN, enabled=False, cond={"assigner_role": ["manager", "department_head"]})  # configurable
r("TASK_CREATED", "ROLE:owner", IN, enabled=False, cond={"assigner_role": ["manager", "department_head", "ceo"]})  # configurable
r("TASK_CREATED", "ACTOR", IN, enabled=False)  # optional confirmation to the assigner
# Head -> Head: everyone is in the loop (the Manager above both, the CEO and the Owner)
_PEER = {"assigner_role": ["department_head"], "assignee_role": ["department_head"]}
r("TASK_CREATED", "ROLE:ceo", cond=_PEER)
r("TASK_CREATED", "ROLE:owner", IN, cond=_PEER)
# --- projects (ADR 003): the head is in the loop; work waits for the head, then for CEO/Owner
r("PROJECT_HEAD_NAMED", "TARGET_USER", mandatory=True)
r("PROJECT_MEMBER_ADDED", "TARGET_USER", BOTH)
# a new project: the CEO and Owner are told (the people on it each get their own mail with the deadline: head named, QA named, added)
r("PROJECT_CREATED", "ROLE:ceo", BOTH)
r("PROJECT_CREATED", "ROLE:owner", BOTH)
# project deadline: the people on the project the day before and on the day; everyone incl. CEO/Owner once it is overdue
for ev in ("PROJECT_DEADLINE_TOMORROW", "PROJECT_DEADLINE_TODAY", "PROJECT_OVERDUE"):
    r(ev, "PROJECT_PEOPLE", BOTH, mandatory=True, urgent=ev != "PROJECT_DEADLINE_TOMORROW")
r("PROJECT_OVERDUE", "ROLE:ceo", BOTH, mandatory=True, urgent=True)
r("PROJECT_OVERDUE", "ROLE:owner", BOTH, mandatory=True, urgent=True)
r("PROJECT_TASK_ASSIGNED", "PROJECT_HEAD", mandatory=True)
r("TASK_HEAD_REVIEW_NEEDED", "PROJECT_HEAD", mandatory=True, urgent=True)
r("TASK_HEAD_APPROVED", "ASSIGNEE", IN)
# --- development flow (ADR 006): assignee -> QA tests (bugs go back to the assignee) -> head -> CEO/Owner
r("PROJECT_QA_NAMED", "TARGET_USER", mandatory=True)
r("TASK_QA_ASSIGNED", "TASK_QA", mandatory=True)
r("TASK_QA_REVIEW_NEEDED", "TASK_QA", mandatory=True, urgent=True)
r("TASK_CREATED", "TASK_LOOP", BOTH)  # everyone on the task's project hears about new work, with the details
r("TASK_QA_APPROVED", "ASSIGNEE", IN)
r("TASK_QA_APPROVED", "TASK_LOOP", IN)
r("TASK_REVIEW_REJECTED", "TASK_LOOP", BOTH)  # bugs found / work sent back: everyone in the loop is told, with the details
r("TASK_REVIEW_APPROVED", "TASK_LOOP", BOTH)  # the task is completed: everyone in the loop is told
r("TASK_SUBMITTED", "TASK_LOOP", IN)
r("TASK_LEADERSHIP_REVIEW_NEEDED", "ROLE:ceo", mandatory=True, urgent=True)
r("TASK_LEADERSHIP_REVIEW_NEEDED", "ROLE:owner", mandatory=True, urgent=True)
r("PROJECT_READY_FOR_REVIEW", "ROLE:ceo", mandatory=True, urgent=True)
r("PROJECT_READY_FOR_REVIEW", "ROLE:owner", mandatory=True, urgent=True)
r("PROJECT_COMPLETED", "PROJECT_HEAD")
r("PROJECT_COMPLETED", "PROJECT_MEMBERS", IN)
# --- a new employee signs up: the Owner(s) are told (in the app and by email); the Admin can edit this rule
r("EMPLOYEE_SIGNED_UP", "ROLE:owner", mandatory=True)
r("EMPLOYEE_SIGNED_UP", "ROLE:admin", mandatory=True)
r("TASK_OWNERSHIP_TAKEN", "ASSIGNEE", IN)
r("TASK_OWNERSHIP_TAKEN", "ASSIGNER", IN)
r("TASK_OWNERSHIP_TAKEN", "DIRECT_MANAGER", IN)
r("TASK_OWNERSHIP_TAKEN", "ANCESTOR_ROLE:manager", IN)
r("TASK_REASSIGNED", "ASSIGNEE", mandatory=True)
r("TASK_REASSIGNED", "PREVIOUS_ASSIGNEE", IN, mandatory=True)
r("TASK_REASSIGNED", "DIRECT_MANAGER", IN)
r("TASK_REASSIGNED", "DEPARTMENT_HEAD", IN)
r("TASK_ACKNOWLEDGED", "ASSIGNER", IN)
r("TASK_ACKNOWLEDGED", "DIRECT_MANAGER", IN)
r("TASK_ACKNOWLEDGED", "ROLE:ceo", IN, enabled=False)
r("TASK_ACKNOWLEDGED", "ROLE:owner", IN, enabled=False)
r("TASK_STARTED", "ASSIGNER", IN)
r("TASK_STARTED", "DIRECT_MANAGER", IN, enabled=False)
r("TASK_PROGRESS", "ASSIGNER", IN)
r("TASK_PROGRESS", "DIRECT_MANAGER", IN, enabled=False)
r("TASK_PRIORITY_CHANGED", "ASSIGNEE", mandatory=True)
r("TASK_PRIORITY_CHANGED", "DIRECT_MANAGER", IN)
r("TASK_ON_HOLD", "ASSIGNEE", IN)
r("TASK_ON_HOLD", "ASSIGNER", IN)
r("TASK_RESUMED_FROM_HOLD", "ASSIGNEE", IN)
# --- finishing and review
r("TASK_COMPLETED", "ASSIGNER")
r("TASK_COMPLETED", "DIRECT_MANAGER")
r("TASK_COMPLETED", "DEPARTMENT_HEAD", IN)
r("TASK_COMPLETED", "ACTOR", IN)  # confirmation to the employee
r("TASK_COMPLETED", "ROLE:ceo", IN, enabled=False)
r("TASK_COMPLETED", "ROLE:owner", IN, enabled=False)
r("TASK_SUBMITTED", "DIRECT_MANAGER")
r("TASK_SUBMITTED", "DEPARTMENT_HEAD")
r("TASK_SUBMITTED", "ASSIGNER")
r("TASK_SUBMITTED", "ACTOR", IN)
r("TASK_REVIEW_APPROVED", "ASSIGNEE", mandatory=True)
r("TASK_REVIEW_REJECTED", "ASSIGNEE", mandatory=True, urgent=True)
r("TASK_VERIFIED", "ASSIGNEE", IN)
r("TASK_REVERTED", "ASSIGNEE", mandatory=True, urgent=True)
r("TASK_REVERTED", "DIRECT_MANAGER", IN)
r("TASK_REVERTED", "ASSIGNER", IN)
r("TASK_CANCELLED", "ASSIGNEE", mandatory=True, urgent=True)
r("TASK_CANCELLED", "DIRECT_MANAGER", IN)
r("TASK_CANCELLED", "ASSIGNER", IN)
# --- deadlines and delays: everyone above is told
for sel in ("ASSIGNEE", "DIRECT_MANAGER", "DEPARTMENT_HEAD", "ROLE:ceo", "ROLE:owner"):
    r("TASK_DEADLINE_CHANGED", sel, mandatory=True, urgent=True)
# A delay reason goes to the employee's Department Head and Manager FIRST. CEO / Owner only hear about it once the line
# has approved it (DELAY_RELEASED), never on submission.
r("DELAY_EXPLANATION_SUBMITTED", "ACTOR", IN)
for sel in ("DIRECT_MANAGER", "DEPARTMENT_HEAD", "ANCESTOR_ROLE:manager"):
    r("DELAY_EXPLANATION_SUBMITTED", sel, BOTH)
r("DELAY_RELEASED", "ROLE:ceo", BOTH)
r("DELAY_RELEASED", "ROLE:owner", BOTH)
r("DELAY_RELEASED", "ASSIGNER", IN)
r("EXTENSION_REQUESTED", "DIRECT_MANAGER")
r("EXTENSION_REQUESTED", "DEPARTMENT_HEAD")
r("EXTENSION_REQUESTED", "ASSIGNER", IN)
r("EXTENSION_REQUESTED", "ANCESTOR_ROLE:manager", IN)
r("EXTENSION_REQUESTED", "ACTOR", IN)
r("EXTENSION_DECIDED", "ASSIGNEE", mandatory=True, urgent=True)
r("DELAY_EXPLANATION_SUBMITTED", "ASSIGNER", IN, cond={"assigner_role": ["manager", "department_head"]})
r("DELAY_REVIEWED", "ASSIGNEE", mandatory=True)
# --- automatic reminders and escalation
r("TASK_REMINDER_24H", "ASSIGNEE", mandatory=True)
r("TASK_REMINDER_2H", "ASSIGNEE", mandatory=True, urgent=True)
for sel in ("ASSIGNEE", "DIRECT_MANAGER", "DEPARTMENT_HEAD", "ANCESTOR_ROLE:manager", "ROLE:ceo", "ROLE:owner"):
    r("TASK_OVERDUE", sel, mandatory=True, urgent=True)
r("TASK_ESCALATION_1", "ASSIGNEE", mandatory=True, urgent=True)  # +1 working day: another reminder to the employee
for sel in ("DIRECT_MANAGER", "DEPARTMENT_HEAD", "ANCESTOR_ROLE:manager", "ROLE:ceo"):  # +3 working days: Manager + CEO
    r("TASK_ESCALATION_2", sel, mandatory=True, urgent=True)
r("TASK_ESCALATION_2", "ASSIGNEE", IN, mandatory=True)
for sel in ("DIRECT_MANAGER", "DEPARTMENT_HEAD", "ANCESTOR_ROLE:manager", "ROLE:ceo", "ROLE:owner"):  # +7: also the Owner
    r("TASK_ESCALATION_3", sel, mandatory=True, urgent=True)
r("TASK_ESCALATION_3", "ASSIGNEE", IN, mandatory=True)
# --- time tracking
r("TIMER_CHECKIN", "ASSIGNEE", IN, mandatory=True)
r("TIMER_AUTO_CLOSED", "ASSIGNEE", mandatory=True)
r("TIME_CORRECTION_REQUESTED", "DIRECT_MANAGER", IN)
r("TIME_CORRECTION_REQUESTED", "DEPARTMENT_HEAD", IN)
r("TIME_CORRECTION_REQUESTED", "ANCESTOR_ROLE:manager", IN)
r("TIME_CORRECTION_APPROVED", "ASSIGNEE", IN, mandatory=True)
r("TIME_CORRECTION_REJECTED", "ASSIGNEE", IN, mandatory=True)
r("TIME_LOG_ADJUSTED", "ASSIGNEE", IN)
r("TIME_UNCONFIRMED_3D", "DIRECT_MANAGER")
r("TIME_UNCONFIRMED_3D", "DEPARTMENT_HEAD", IN)

# --- blockers: the Manager line hears at once (they stop work); CEO/Owner only for critical tasks
r("BLOCKER_RAISED", "ACTOR", IN)
r("BLOCKER_RAISED", "DIRECT_MANAGER", urgent=True)
r("BLOCKER_RAISED", "DEPARTMENT_HEAD", urgent=True)
r("BLOCKER_RAISED", "ANCESTOR_ROLE:manager", urgent=True)
r("BLOCKER_RAISED", "ASSIGNER", IN)
r("BLOCKER_RAISED", "ROLE:ceo", urgent=True, cond={"priority": ["critical"]})
r("BLOCKER_RAISED", "ROLE:owner", urgent=True, cond={"priority": ["critical"]})
r("BLOCKER_ACKNOWLEDGED", "BLOCKER_RAISER", IN, mandatory=True)
r("BLOCKER_ASSIGNED", "BLOCKER_OWNER", mandatory=True)
r("BLOCKER_ASSIGNED", "BLOCKER_RAISER", IN)
r("BLOCKER_IN_PROGRESS", "BLOCKER_RAISER", IN)
r("BLOCKER_REPLIED", "BLOCKER_RAISER")
r("BLOCKER_REPLIED", "BLOCKER_OWNER", IN)
r("BLOCKER_REPLIED", "DIRECT_MANAGER", IN)
r("BLOCKER_RESOLVED", "BLOCKER_RAISER", mandatory=True)
r("BLOCKER_RESOLVED", "DIRECT_MANAGER")
r("BLOCKER_RESOLVED", "ASSIGNER", IN)
r("BLOCKER_RESOLVED", "ROLE:ceo", IN, enabled=False)
r("BLOCKER_RESOLVED", "ROLE:owner", IN, enabled=False)
r("BLOCKER_CLOSED", "DIRECT_MANAGER", IN)
r("BLOCKER_CLOSED", "BLOCKER_OWNER", IN)
r("BLOCKER_REOPENED", "DIRECT_MANAGER", urgent=True)
r("BLOCKER_REOPENED", "DEPARTMENT_HEAD", urgent=True)
r("BLOCKER_REOPENED", "BLOCKER_OWNER", IN)
for sel in ("DEPARTMENT_HEAD", "ANCESTOR_ROLE:manager", "ROLE:ceo", "ROLE:owner"):
    r("BLOCKER_ESCALATED", sel, mandatory=True, urgent=True)
r("BLOCKER_ESCALATED", "BLOCKER_RAISER", IN)
# --- the discussion
r("COMMENT_ADDED", "MENTIONED")
r("COMMENT_ADDED", "COMMENT_PARENT_AUTHOR", IN)
r("COMMENT_ADDED", "ASSIGNEE", IN)
r("COMMENT_ADDED", "ASSIGNER", IN)
# ADR 006: every comment, question and reply goes, in full, to everybody in the loop of the task and its project (app + email)
r("COMMENT_ADDED", "TASK_LOOP", BOTH, mandatory=True)
r("QUESTION_ASKED", "TASK_LOOP", BOTH, mandatory=True)
r("BLOCKER_RAISED", "TASK_LOOP", BOTH)
r("BLOCKER_REPLIED", "TASK_LOOP", BOTH)
r("BLOCKER_RESOLVED", "TASK_LOOP", BOTH)
r("QUESTION_ASKED", "MENTIONED")
r("QUESTION_ASKED", "ASSIGNER")
r("QUESTION_ASKED", "DIRECT_MANAGER", IN)
r("QUESTION_ASKED", "DEPARTMENT_HEAD", IN)
r("QUESTION_ASKED", "ASSIGNEE", IN)

PRE = "assigned,acknowledged,in_progress,blocked,reopened"  # not on hold, not waiting for review, not finished
# (code, kind, minutes, working_days, event, statuses, order)
REMINDERS = [
    ("before_24h", "before", 1440, 0, "TASK_REMINDER_24H", PRE, 10),
    ("before_2h", "before", 120, 0, "TASK_REMINDER_2H", PRE, 20),
    ("at_due", "at_due", 0, 0, "TASK_OVERDUE", PRE, 30),
    ("after_1d", "after_working_days", 0, 1, "TASK_ESCALATION_1", PRE, 40),
    ("after_3d", "after_working_days", 0, 3, "TASK_ESCALATION_2", PRE, 50),
    ("after_7d", "after_working_days", 0, 7, "TASK_ESCALATION_3", PRE, 60),
]


RULES_VERSION = 5  # 2: delay explanations reach CEO/Owner only after approval; head-to-head loop; head ownership
REWRITTEN = {"DELAY_EXPLANATION_SUBMITTED", "PROJECT_MEMBER_ADDED"}  # rule sets replaced wholesale when upgrading an older database


def _upgrade_existing(db: Session) -> None:
    """One-time upgrade of rules on a database seeded before RULES_VERSION (later Admin edits are never touched)."""
    from app.modules.audit.models import SystemSetting

    row = db.get(SystemSetting, "notification_rules_version")
    current = row.value if row is not None and isinstance(row.value, int) else 0
    have = set(db.scalars(select(NotificationRule.event_type).distinct()))
    if current < RULES_VERSION and have:  # an existing install (fresh installs are seeded with the new rules below)
        for ev in REWRITTEN & have:
            db.execute(delete(NotificationRule).where(NotificationRule.event_type == ev))
        have -= REWRITTEN
        for event, selector, channels, mandatory, urgent, enabled, cond in _R:
            if event in have and not any(x.selector == selector and x.condition_json == cond for x in db.scalars(select(NotificationRule).where(NotificationRule.event_type == event))):
                db.add(NotificationRule(event_type=event, selector=selector, channels=channels, mandatory=mandatory, urgent=urgent, enabled=enabled, condition_json=cond))
        db.flush()
    if row is None:
        db.add(SystemSetting(key="notification_rules_version", value=RULES_VERSION))
    elif current < RULES_VERSION:
        row.value = RULES_VERSION


def seed_notifications(db: Session) -> None:
    _upgrade_existing(db)
    have = set(db.scalars(select(NotificationRule.event_type).distinct()))
    for event, selector, channels, mandatory, urgent, enabled, cond in _R:
        if event in have:
            continue
        db.add(NotificationRule(event_type=event, selector=selector, channels=channels, mandatory=mandatory, urgent=urgent, enabled=enabled, condition_json=cond))
    codes = set(db.scalars(select(ReminderRule.code)))
    for code, kind, minutes, wdays, event, statuses, order in REMINDERS:
        if code not in codes:
            db.add(ReminderRule(code=code, kind=kind, minutes=minutes, working_days=wdays, event_type=event, statuses=statuses, sort_order=order))
    db.flush()
