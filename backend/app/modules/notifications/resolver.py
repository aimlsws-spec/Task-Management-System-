"""Who should be told? Rules name RELATIONS (assignee, their manager, the department head, everyone with a role);
this module turns them into real people for one event, using the hierarchy as it is right now."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.notifications.models import NotificationPreference, NotificationRule
from app.modules.org.models import Department, Employee, ReportingRelationship
from app.modules.rbac.models import Role, UserRole
from app.modules.tasks import loop
from app.modules.tasks.models import Task


@dataclass
class Recipient:
    user_id: int
    reasons: set[str] = field(default_factory=set)
    channels: set[str] = field(default_factory=set)
    mandatory: bool = False
    urgent: bool = False


def _user_of(db: Session, employee_id: int | None) -> int | None:
    return db.scalar(select(Employee.user_id).where(Employee.id == employee_id)) if employee_id else None


def manager_chain(db: Session, employee_id: int) -> list[int]:
    """Employee ids above this person, nearest first (current primary reporting lines; cycle-safe)."""
    chain: list[int] = []
    cur = employee_id
    for _ in range(12):
        nxt = db.scalar(
            select(ReportingRelationship.reports_to_id).where(
                ReportingRelationship.employee_id == cur, ReportingRelationship.relation_type == "primary",
                ReportingRelationship.effective_to.is_(None),
            )
        )
        if nxt is None or nxt in chain:
            break
        chain.append(nxt)
        cur = nxt
    return chain


def role_codes(db: Session, user_id: int | None) -> set[str]:
    if user_id is None:
        return set()
    return set(db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)))


def _users_with_role(db: Session, code: str) -> list[int]:
    return list(db.scalars(select(User.id).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id).where(Role.code == code, User.is_active.is_(True))))


def _selector_users(db: Session, selector: str, task: Task | None, actor_user_id: int | None, payload: dict) -> list[int]:
    kind, _, arg = selector.partition(":")
    if kind == "ACTOR":
        return [actor_user_id] if actor_user_id else []
    if kind == "ROLE":
        return _users_with_role(db, arg)
    after = payload.get("after") or {}
    if kind == "COMPANY_CEO":
        cid = after.get("company_id")
        if not cid:
            return []
        from app.modules.org.models import CompanyCEO
        return list(
            db.scalars(
                select(CompanyCEO.user_id)
                .join(User, User.id == CompanyCEO.user_id)
                .where(CompanyCEO.company_id == cid, User.is_active.is_(True))
            )
        )
    if kind in ("PROJECT_HEAD", "PROJECT_MEMBERS"):  # the project of the task, or named in the event
        from app.modules.tasks.models import Project, ProjectMember

        if kind == "PROJECT_HEAD" and task is not None:  # the task's head: its own, else its project's (a task needs no project)
            return [u for u in (_user_of(db, loop.head_id(db, task)),) if u]
        pid = (task.project_id if task is not None else None) or after.get("project_id")
        if not pid:
            return []
        if kind == "PROJECT_HEAD":
            head = db.scalar(select(Project.head_employee_id).where(Project.id == pid))
            return [u for u in (_user_of(db, head),) if u]
        ids = db.scalars(select(ProjectMember.employee_id).where(ProjectMember.project_id == pid))
        return [u for u in (_user_of(db, i) for i in ids) if u]
    if kind == "PROJECT_PEOPLE":  # everyone on the project: head, QA, team and creator
        from app.modules.tasks.models import Project, ProjectMember

        pid = (task.project_id if task is not None else None) or after.get("project_id")
        pr = db.get(Project, pid) if pid else None
        if pr is None:
            return []
        ids = [pr.head_employee_id, pr.qa_employee_id, pr.owner_employee_id, *db.scalars(select(ProjectMember.employee_id).where(ProjectMember.project_id == pr.id))]
        return [u for u in dict.fromkeys(_user_of(db, i) for i in ids if i) if u]
    if kind == "TARGET_USER":  # one named person (e.g. someone just added to a project)
        return [int(after["user_id"])] if after.get("user_id") else []
    if kind == "MENTIONED":  # people @mentioned in a comment
        return [int(u) for u in after.get("mentions", [])]
    if kind == "BLOCKER_RAISER":
        return [after["raised_by_user_id"]] if after.get("raised_by_user_id") else []
    if kind == "BLOCKER_OWNER":
        return [after["owner_user_id"]] if after.get("owner_user_id") else []
    if kind == "COMMENT_PARENT_AUTHOR":  # the author of the comment being replied to
        return [after["parent_author_user_id"]] if after.get("parent_author_user_id") else []
    if task is None:
        return []
    if kind == "TASK_QA":  # the QA of this task (its own, else its project's)
        return [u for u in (_user_of(db, loop.qa_id(db, task)),) if u]
    if kind == "TASK_LOOP":  # everyone in the loop: the task's people and the project's head, QA, team and creator
        return [u for u in (_user_of(db, e) for e in loop.loop_employee_ids(db, task)) if u]
    if kind == "ASSIGNEE":
        return [u for u in (_user_of(db, task.assignee_id),) if u]
    if kind == "ASSIGNER":
        return [u for u in (_user_of(db, task.assigned_by_id),) if u]
    if kind == "PREVIOUS_ASSIGNEE":
        return [u for u in (_user_of(db, (payload.get("before") or {}).get("assignee_id")),) if u]
    chain = manager_chain(db, task.assignee_id)
    if kind == "DIRECT_MANAGER":
        return [u for u in (_user_of(db, chain[0] if chain else None),) if u]
    if kind == "MANAGER_CHAIN":
        return [u for u in (_user_of(db, e) for e in chain) if u]
    if kind == "ANCESTOR_ROLE":
        return [u for u in (_user_of(db, e) for e in chain) if u and arg in role_codes(db, u)]
    if kind == "DEPARTMENT_HEAD":
        head = db.scalar(select(Department.head_employee_id).where(Department.id == task.department_id))
        return [u for u in (_user_of(db, head if head != task.assignee_id else None),) if u]
    return []


def _condition_ok(db: Session, cond: dict | None, task: Task | None, actor_user_id: int | None) -> bool:
    """Optional narrowing of a rule, e.g. {"assigner_role": ["owner"]} or {"priority": ["critical", "high"]}."""
    if not cond:
        return True
    if "assigner_role" in cond:
        assigner = _user_of(db, task.assigned_by_id) if task else None
        if not role_codes(db, assigner) & set(cond["assigner_role"]):
            return False
    if "assignee_role" in cond:
        assignee = _user_of(db, task.assignee_id) if task else None
        if not role_codes(db, assignee) & set(cond["assignee_role"]):
            return False
    if "actor_role" in cond and not role_codes(db, actor_user_id) & set(cond["actor_role"]):
        return False
    if "priority" in cond and (task is None or task.priority not in cond["priority"]):
        return False
    return True


def resolve(db: Session, event_type: str, task: Task | None, actor_user_id: int | None, payload: dict) -> dict[int, Recipient]:
    """People to notify for this event, merged so each person gets ONE notification listing all their reasons."""
    out: dict[int, Recipient] = {}
    rules = db.scalars(select(NotificationRule).where(NotificationRule.event_type == event_type, NotificationRule.enabled.is_(True))).all()
    for rule in rules:
        if not _condition_ok(db, rule.condition_json, task, actor_user_id):
            continue
        for uid in _selector_users(db, rule.selector, task, actor_user_id, payload):
            if uid == actor_user_id and rule.selector != "ACTOR":
                continue  # you are not told about what you just did yourself (unless it is a confirmation rule)
            r = out.setdefault(uid, Recipient(uid))
            r.reasons.add(rule.selector)
            r.channels |= {c.strip() for c in rule.channels.split(",") if c.strip()}
            r.mandatory = r.mandatory or rule.mandatory
            r.urgent = r.urgent or rule.urgent
    # Only active people
    active = set(db.scalars(select(User.id).where(User.id.in_(list(out)), User.is_active.is_(True)))) if out else set()
    out = {u: r for u, r in out.items() if u in active}
    if event_type == "BLOCKER_RAISED":
        has_head = bool(task and loop.head_id(db, task) and loop.head_id(db, task) != task.assignee_id)
        if has_head:
            head_user_id = _user_of(db, loop.head_id(db, task))
            for uid in list(out.keys()):
                if uid != head_user_id and role_codes(db, uid) & {"owner", "ceo"}:
                    del out[uid]
    # Personal preferences (mandatory notices cannot be muted)
    if out:
        muted = {(p.user_id, p.channel) for p in db.scalars(select(NotificationPreference).where(NotificationPreference.event_type == event_type, NotificationPreference.enabled.is_(False), NotificationPreference.user_id.in_(list(out))))}
        for uid, r in list(out.items()):
            if not r.mandatory:
                r.channels = {c for c in r.channels if (uid, c) not in muted}
            if not r.channels:
                del out[uid]
    return out
