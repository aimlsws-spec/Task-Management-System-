"""Words for each kind of event, and the email layout. Text is always escaped before it goes into HTML."""

from datetime import UTC, datetime
from html import escape
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.core.config import get_settings

# Plain-language names shown on the notification settings page.
EVENT_LABELS: dict[str, str] = {
    "TASK_CREATED": "A task is assigned", "TASK_REASSIGNED": "A task is reassigned", "TASK_ACKNOWLEDGED": "A task is acknowledged",
    "TASK_STARTED": "Work starts on a task", "TASK_PROGRESS": "Progress is reported", "TASK_PRIORITY_CHANGED": "Priority changes",
    "TASK_ON_HOLD": "A task is put on hold", "TASK_RESUMED_FROM_HOLD": "A task resumes after hold", "TASK_COMPLETED": "A task is completed",
    "TASK_SUBMITTED": "Work is submitted for review", "TASK_REVIEW_APPROVED": "Review approved", "TASK_REVIEW_REJECTED": "Review sent back",
    "TASK_VERIFIED": "A completion is verified", "TASK_REVERTED": "Completed work is reverted", "TASK_CANCELLED": "A task is cancelled",
    "TASK_DEADLINE_CHANGED": "A deadline changes", "EXTENSION_REQUESTED": "More time is requested", "EXTENSION_DECIDED": "An extension request is decided",
    "DELAY_EXPLANATION_SUBMITTED": "A delay explanation is submitted", "DELAY_REVIEWED": "A delay explanation is reviewed",
    "TASK_REMINDER_24H": "Deadline in 24 hours", "TASK_REMINDER_3H": "Deadline in 3 hours (before EOD)", "TASK_REMINDER_2H": "Deadline in 2 hours", "TASK_OVERDUE": "A task becomes overdue",
    "TASK_ESCALATION_1": "Overdue: 1 working day", "TASK_ESCALATION_2": "Overdue: 3 working days (escalation)",
    "TASK_ESCALATION_3": "Overdue: 7 working days (escalation)", "TIMER_CHECKIN": "'Still working?' timer check-in",
    "TIMER_AUTO_CLOSED": "A timer was stopped automatically", "TIME_CORRECTION_REQUESTED": "Missing time is requested",
    "TIME_CORRECTION_APPROVED": "Missing time approved", "TIME_CORRECTION_REJECTED": "Missing time declined",
    "TIME_LOG_ADJUSTED": "A time entry is adjusted",
    "BLOCKER_RAISED": "A blocker is reported", "BLOCKER_ACKNOWLEDGED": "A blocker is acknowledged", "BLOCKER_ASSIGNED": "A blocker is assigned to someone",
    "BLOCKER_IN_PROGRESS": "Work starts on a blocker", "BLOCKER_REPLIED": "Someone replies on a blocker", "BLOCKER_RESOLVED": "A blocker is resolved",
    "BLOCKER_CLOSED": "A blocker is closed", "BLOCKER_REOPENED": "A blocker is reopened", "BLOCKER_ESCALATED": "A blocker is escalated",
    "COMMENT_ADDED": "A comment is added or you are mentioned", "QUESTION_ASKED": "A question is asked", "TIME_UNCONFIRMED_3D": "Auto-stopped time unconfirmed for 3 days",
    "EMPLOYEE_SIGNED_UP": "A new employee signs up", "PROJECT_HEAD_NAMED": "You are named head of a project",
    "PROJECT_MEMBER_ADDED": "You are added to a project team", "PROJECT_TASK_ASSIGNED": "A task is assigned in a project you head",
    "TASK_HEAD_REVIEW_NEEDED": "Finished work needs the project head's approval", "TASK_HEAD_APPROVED": "The project head approved your work",
    "TASK_LEADERSHIP_REVIEW_NEEDED": "Finished project work is ready for CEO/Owner review", "PROJECT_READY_FOR_REVIEW": "A project is ready to be completed",
    "PROJECT_COMPLETED": "A project is completed", "PROJECT_CREATED": "A project is created", "PROJECT_DEADLINE_TOMORROW": "A project is due tomorrow",
    "PROJECT_DEADLINE_TODAY": "A project is due today", "PROJECT_DEADLINE_3H": "Project due in 3 hours (before EOD)", "PROJECT_OVERDUE": "A project is overdue", "PROJECT_QA_NAMED": "You are named QA of a project",
    "TASK_QA_ASSIGNED": "You are the QA of a task", "TASK_QA_REVIEW_NEEDED": "Finished work needs QA testing",
    "TASK_QA_APPROVED": "QA passed the work and confirmed the bugs are solved",
    "DELAY_RELEASED": "A delay explanation is approved and shared with leadership", "TASK_OWNERSHIP_TAKEN": "A Department Head takes ownership of a task",
}


def when(dt: datetime | None, tz: str) -> str:
    if dt is None:
        return "—"
    return dt.replace(tzinfo=UTC).astimezone(ZoneInfo(tz)).strftime("%d %b %Y, %I:%M %p").lstrip("0")


def _c(a: dict, key: str, default: str = "") -> str:
    return str(a.get(key) or default)


def _pfacts(a: dict) -> str:
    """Deadline and expected result of a project, appended to the mails of everyone added to it."""
    out = []
    if a.get("ends_on"):
        out.append(f"Project deadline: {datetime.fromisoformat(str(a['ends_on'])).strftime('%d %b %Y')}")
    if a.get("expected_result"):
        out.append(f"Expected result: {a['expected_result']}")
    return ("\n\n" + "\n".join(out)) if out else ""


def _in(a: dict) -> str:
    return f" in {a['project']}" if a.get("project") else ""


def _c_project(c: SimpleNamespace) -> str:
    return f" (project {c.project})" if getattr(c, "project", "") else ""


def _people(c: SimpleNamespace) -> str:
    """Who this message went to and where the task stands: every detail, so nobody has to open the app to follow along."""
    names = getattr(c, "people", None) or []
    lines = [f"Task status: {getattr(c, 'status', '').replace('_', ' ')}", f"Assigned to: {c.assignee}"]
    if getattr(c, "head", ""):
        lines.append(f"Head: {c.head}")
    if getattr(c, "qa", ""):
        lines.append(f"QA: {c.qa}")
    if names:
        lines.append("In this conversation: " + ", ".join(names))
    return "\n\n" + "\n".join(lines)


def render(event_type: str, c: SimpleNamespace) -> tuple[str, str]:
    """(title, body) for one recipient. `c` has: actor, task_no, title, assignee, assigner, priority, due, hours, a (after), b (before)."""
    a, b, who = c.a or {}, c.b or {}, c.actor or "Someone"
    t = f'{c.task_no} "{c.title}"'
    table = {
        "PROJECT_HEAD_NAMED": (f"You head the project {_c(a, 'project')}", f"{who} made you the head of {_c(a, 'project')}. You will be told about its tasks and approve finished work before it goes to the CEO/Owner.{_pfacts(a)}"),
        "PROJECT_MEMBER_ADDED": (f"Added to project {_c(a, 'project')}", f"{who} added you to the team of {_c(a, 'project')}. Tasks for this project will appear in your list.{_pfacts(a)}"),
        "PROJECT_CREATED": (f"New project: {_c(a, 'project')}", f"{who} created the project {_c(a, 'project')}.{_pfacts(a)}\n\nHead: {_c(a, 'head', 'none')}\nQA: {_c(a, 'qa', 'none')}\nTeam: {_c(a, 'team', 'not chosen yet')}"),
        "PROJECT_DEADLINE_TOMORROW": (f"Project due tomorrow: {_c(a, 'project')}", f"The deadline of the project {_c(a, 'project')} is tomorrow.{_pfacts(a)}"),
        "PROJECT_DEADLINE_TODAY": (f"Project due today: {_c(a, 'project')}", f"The deadline of the project {_c(a, 'project')} is today.{_pfacts(a)}"),
        "PROJECT_DEADLINE_3H": (f"Project due in 3 hours: {_c(a, 'project')}", f"The deadline of the project {_c(a, 'project')} is in 3 hours (today at 6:30 PM / EOD). Please ensure all pending tasks are completed and submitted.{_pfacts(a)}"),
        "PROJECT_OVERDUE": (f"Project overdue: {_c(a, 'project')}", f"The deadline of the project {_c(a, 'project')} has passed and it is not completed.{_pfacts(a)}"),
        "PROJECT_QA_NAMED": (f"You are QA for the project {_c(a, 'project')}", f"{who} made you the QA of {_c(a, 'project')}. You will test finished work and report bugs before it goes to the head and the CEO/Owner.{_pfacts(a)}"),
        "TASK_QA_ASSIGNED": (f"You are QA for: {c.title}", f"{who} added you as the QA of {t} (assigned to {c.assignee}){_in(a)}. When {c.assignee} finishes it you will be asked to test it."),
        "TASK_QA_REVIEW_NEEDED": (f"Please test: {c.title}", f"{c.assignee} finished {t}{_in(a)}. Test it: report the bugs you find (it goes back to {c.assignee} to fix) or confirm it is bug-free to send it to the head."),
        "TASK_QA_APPROVED": (f"QA passed: {c.title}", f"{who} (QA) tested {t} and confirmed the bugs are solved. It now goes to the head for review. {_c(a, 'note')}".strip()),
        "PROJECT_TASK_ASSIGNED": (f"New task for you to oversee: {c.title}", f"{who} assigned {t} to {c.assignee}{_in(a)}. Priority {c.priority}, due {c.due}."),
        "TASK_HEAD_REVIEW_NEEDED": (f"Please approve: {c.title}", f"{c.assignee} finished {t}{_in(a)}, and it passed testing where QA is involved. Approve it to send it to the CEO/Owner, or send it back."),
        "TASK_HEAD_APPROVED": (f"Approved by the head: {c.title}", f"{who} approved {t}. It now waits for the CEO/Owner review."),
        "TASK_LEADERSHIP_REVIEW_NEEDED": (f"Review needed: {c.title}", f"{t}{_in(a)} was finished by {c.assignee} and is ready for your review."),
        "PROJECT_READY_FOR_REVIEW": (f"Project ready: {_c(a, 'project')}", f"Every task in {_c(a, 'project')} is done. Open the project and mark it completed when you are satisfied."),
        "PROJECT_COMPLETED": (f"Project completed: {_c(a, 'project')}", f"{who} marked {_c(a, 'project')} completed."),
        "EMPLOYEE_SIGNED_UP": (
            f"New sign-up: {_c(a, 'name')} ({_c(a, 'role')})" if _c(a, 'role') and _c(a, 'role') != "Employee" else f"New sign-up: {_c(a, 'name')}",
            f"{_c(a, 'name')} ({_c(a, 'email')}) joined as {_c(a, 'role')}." if not a.get("needs_onboarding", _c(a, "role", "Employee") == "Employee") else f"{_c(a, 'name')} ({_c(a, 'email')}) just signed up and will choose their department next.",
        ),
        "TASK_CREATED": (f"New task: {c.title}", f"{who} assigned {t} to {c.assignee}. Priority {c.priority}, due {c.due}."),
        "TASK_REASSIGNED": (f"Task reassigned: {c.title}", f"{t} now belongs to {c.assignee}. {_c(a, 'reason')}".strip()),
        "TASK_ACKNOWLEDGED": (f"Acknowledged: {c.title}", f"{who} acknowledged {t}."),
        "TASK_STARTED": (f"Work started: {c.title}", f"{who} started working on {t}."),
        "TASK_PROGRESS": (f"Progress {_c(a, 'progress_pct')}%: {c.title}", f"{who}: {_c(a, 'note')}"),
        "TASK_PRIORITY_CHANGED": (f"Priority changed: {c.title}", f"{t}: {_c(b, 'priority')} → {_c(a, 'priority')}. {_c(a, 'reason')}".strip()),
        "TASK_ON_HOLD": (f"On hold: {c.title}", f"{t} was put on hold. {_c(a, 'reason')}".strip()),
        "TASK_RESUMED_FROM_HOLD": (f"Resumed: {c.title}", f"{t} is back in progress."),
        "TASK_COMPLETED": (f"Completed: {c.title}", f"{who} marked {t} complete. {_c(a, 'summary')}".strip()),
        "TASK_SUBMITTED": (f"Needs review: {c.title}", f"{who} submitted {t} for review. {_c(a, 'summary')}".strip()),
        "TASK_REVIEW_APPROVED": (f"Completed: {c.title}", f"{who} reviewed and approved {t}{_c_project(c)}. The task is completed. {_c(a, 'note')}".strip()),
        "TASK_REVIEW_REJECTED": (f"{'Bugs found' if a.get('stage') == 'qa' else 'Sent back'}: {c.title}", f"{who} {'(QA) found problems in' if a.get('stage') == 'qa' else 'sent back'} {t}{_c_project(c)}. {c.assignee} must fix and submit it again.\n\nWhat is wrong:\n{_c(a, 'reason')}" + (f"\n\nBug sheet: {a['bug_sheet_url']}" if a.get("bug_sheet_url") else "").strip()),
        "TASK_VERIFIED": (f"Verified: {c.title}", f"{who} verified {t}."),
        "TASK_REVERTED": (f"Reverted: {c.title}", f"{who} sent {t} back for rework ({_c(a, 'reason_code').replace('_', ' ')}). {_c(a, 'reason')}" + (f"\n\nBug sheet: {a['bug_sheet_url']}" if a.get("bug_sheet_url") else "").strip()),
        "TASK_CANCELLED": (f"Cancelled: {c.title}", f"{who} cancelled {t}. {_c(a, 'reason')}".strip()),
        "TASK_DEADLINE_CHANGED": (f"Deadline changed: {c.title}", f"{who} changed the deadline of {t} to {c.due_after}. Reason: {_c(a, 'reason')}"),
        "EXTENSION_REQUESTED": (f"Extension requested: {c.title}", f"{who} asked for more time on {t}. {_c(a, 'reason')}".strip()),
        "EXTENSION_DECIDED": (f"Extension {_c(a, 'decision')}: {c.title}", f"{who} {_c(a, 'decision')} your request for more time on {t}. {_c(a, 'note')}".strip()),
        "DELAY_EXPLANATION_SUBMITTED": (f"Delay explained: {c.title}", f"{who} explained why {t} is late: {_c(a, 'reason')}"),
        "DELAY_RELEASED": (f"Delay approved: {c.title}", f"{who} approved the reason for the delay on {t} ({c.assignee}): {_c(a, 'reason')}"),
        "TASK_OWNERSHIP_TAKEN": (f"Head took ownership: {c.title}", f"{who} took responsibility for {t}. {_c(a, 'note')}".strip()),
        "DELAY_REVIEWED": (f"Your delay explanation was reviewed: {c.title}", f"{who}: {_c(a, 'decision').replace('_', ' ')}. {_c(a, 'comment')}".strip()),
        "TASK_REMINDER_24H": (f"Due in 24 hours: {c.title}", f"{t} is due {c.due}. Please complete it before the deadline."),
        "TASK_REMINDER_3H": (f"Due in 3 hours: {c.title}", f"{t} is due {c.due} (in 3 hours / 6:30 PM EOD) and is still open. Please finish and submit your work before the deadline."),
        "TASK_REMINDER_2H": (f"Due in 2 hours: {c.title}", f"{t} is due {c.due} and is still open."),
        "TASK_OVERDUE": (f"Overdue: {c.title}", f"{t} (assigned to {c.assignee}) passed its deadline of {c.due}. A reason for the delay is required."),
        "TASK_ESCALATION_1": (f"Still overdue: {c.title}", f"{t} is one working day past its deadline ({c.due}). Please complete it or explain the delay."),
        "TASK_ESCALATION_2": (f"Escalation: {c.title}", f"{t} (assigned to {c.assignee}) is three working days past its deadline ({c.due})."),
        "TASK_ESCALATION_3": (f"Escalation: {c.title}", f"{t} (assigned to {c.assignee}) is seven working days past its deadline ({c.due})."),
        "TIMER_CHECKIN": (f"Still working on {c.task_no}?", f"Your timer on {t} has been running for a long time. Continue or stop it so your time stays accurate."),
        "TIMER_AUTO_CLOSED": (f"Your timer was stopped: {c.task_no}", f"The timer on {t} ran past the daily limit and was stopped automatically. Please confirm or shorten the time."),
        "TIME_CORRECTION_REQUESTED": (f"Missing time requested: {c.title}", f"{who} asked to add missing time on {t}. Please review it."),
        "TIME_CORRECTION_APPROVED": (f"Missing time approved: {c.title}", f"{who} approved the time you added on {t}."),
        "TIME_CORRECTION_REJECTED": (f"Missing time declined: {c.title}", f"{who} declined the time you added on {t}. {_c(a, 'note')}".strip()),
        "TIME_LOG_ADJUSTED": (f"Time entry adjusted: {c.title}", f"{who} adjusted one of your time entries on {t}. {_c(a, 'reason')}".strip()),
        "BLOCKER_RAISED": (f"Blocked: {c.title}", f"{who} reported a blocker on {t}: {_c(a, 'title')}. Impact: {_c(a, 'impact', 'not stated')}. {'Work is stopped.' if a.get('blocks_work') else 'Work can continue.'}"),
        "BLOCKER_ACKNOWLEDGED": (f"Blocker acknowledged: {c.title}", f"{who} acknowledged your blocker \"{_c(a, 'title')}\"."),
        "BLOCKER_ASSIGNED": (f"Blocker assigned: {c.title}", f"{who} asked you to deal with the blocker \"{_c(a, 'title')}\" on {t}."),
        "BLOCKER_IN_PROGRESS": (f"Blocker in progress: {c.title}", f"{who} started working on the blocker \"{_c(a, 'title')}\"."),
        "BLOCKER_REPLIED": (f"Blocker reply: {c.title}", f"{who} on \"{_c(a, 'title')}\": {_c(a, 'note')}"),
        "BLOCKER_RESOLVED": (f"Blocker resolved: {c.title}", f"{who} resolved \"{_c(a, 'title')}\": {_c(a, 'note')}. You can continue work on {t}."),
        "BLOCKER_CLOSED": (f"Blocker closed: {c.title}", f"{who} closed the blocker \"{_c(a, 'title')}\"."),
        "BLOCKER_REOPENED": (f"Blocker reopened: {c.title}", f"{who} reopened \"{_c(a, 'title')}\" on {t}: it is still a problem."),
        "BLOCKER_ESCALATED": (f"Blocker escalated: {c.title}", f"{who} escalated \"{_c(a, 'title')}\" on {t}. {_c(a, 'note')}".strip()),
        "COMMENT_ADDED": (f"{('Reply' if a.get('kind') == 'reply' else 'Comment')} on {c.task_no}: {c.title}", f"{who} wrote on {t}{_c_project(c)}:\n\n{_c(a, 'body')}{_people(c)}"),
        "QUESTION_ASKED": (f"Question on {c.task_no}: {c.title}", f"{who} asked on {t}{_c_project(c)}:\n\n{_c(a, 'body')}{_people(c)}"),
        "TIME_UNCONFIRMED_3D": (f"Unconfirmed time: {c.title}", f"Auto-stopped time on {t} by {c.assignee} has not been confirmed for 3 days."),
    }
    return table.get(event_type, (f"{event_type.replace('_', ' ').title()}: {c.title}", f"{who}: {t}"))


def email_bodies(title: str, body: str, link: str, urgent: bool, cta: str = "Open the task") -> tuple[str, str]:
    try:
        s = get_settings()
        base_url = s.app_base_url.rstrip("/")
    except Exception:
        base_url = "https://tksf.seawind.co.in"
    base_display = base_url.replace("https://", "").replace("http://", "")
    logo_url = "cid:seawind_logo"

    text = f"{title}\n\n{body}\n\n{cta}: {link}\n\n— SeaWind Task Management\nRegeneration of IT Services\n{base_url}"
    urgent_banner = (
        '<tr><td style="padding:0 32px 16px;">'
        '<div style="display:inline-block;background-color:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:4px 10px;">'
        '<span style="color:#b91c1c;font-size:11px;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;">Attention Required</span>'
        '</div></td></tr>'
    ) if urgent else ""

    button_markup = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 8px;">'
        f'<tr><td style="border-radius:8px;background-color:#1f55c4;">'
        f'<a href="{escape(link, quote=True)}" target="_blank" style="display:inline-block;padding:12px 24px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;font-size:14px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;background-color:#1f55c4;box-shadow:0 2px 4px rgba(31,85,196,0.25);">'
        f'{escape(cta)} &rarr;</a>'
        f'</td></tr></table>'
    ) if link else ""

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1e293b;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f1f5f9;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;background-color:#ffffff;border-radius:14px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 4px 12px rgba(15,23,42,0.06);">
          
          <!-- Top Brand Accent Bar -->
          <tr>
            <td style="height:4px;background:linear-gradient(90deg,#1e3a8a 0%,#1f55c4 50%,#0284c7 100%);line-height:4px;font-size:4px;">&nbsp;</td>
          </tr>

          <!-- Header with SeaWind Logo -->
          <tr>
            <td style="padding:24px 32px 18px;border-bottom:1px solid #f1f5f9;background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="left" style="vertical-align:middle;">
                    <a href="{base_url}" target="_blank" style="text-decoration:none;display:inline-block;">
                      <img src="{logo_url}" alt="SeaWind - Regeneration of IT Services" width="165" style="display:block;width:165px;max-width:165px;height:auto;border:0;outline:none;" />
                    </a>
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    <span style="display:inline-block;background-color:#eff6ff;color:#1d4ed8;font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:4px 10px;border-radius:9999px;border:1px solid #bfdbfe;">
                      Task Management
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          {urgent_banner}

          <!-- Content Body -->
          <tr>
            <td style="padding:28px 32px 24px;">
              <h1 style="margin:0 0 14px;font-size:20px;font-weight:700;line-height:1.35;color:#0f172a;">
                {escape(title)}
              </h1>
              <div style="font-size:14px;line-height:1.65;color:#334155;white-space:pre-wrap;margin:0 0 16px;">{escape(body)}</div>
              {button_markup}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;background-color:#f8fafc;border-top:1px solid #e2e8f0;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-size:12px;line-height:1.6;color:#64748b;">
                    <strong style="color:#334155;">SeaWind Solution</strong> &bull; Regeneration of IT Services<br />
                    Workspace: <a href="{base_url}" target="_blank" style="color:#1f55c4;text-decoration:none;">{base_display}</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:10px;font-size:11px;line-height:1.5;color:#94a3b8;">
                    This is an automated operational notification regarding your tasks and assignments. Please do not reply directly to this email.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>'''
    return text, html


def invite_email(role_name: str, email: str, link: str, has_account: bool) -> tuple[str, str, str]:
    """(subject, text, html) for the email an Admin's role registration sends to that address."""
    if has_account:
        subject = f"[SeaWind] You are now {role_name} in SeaWind Task Management"
        body = f"The administrator made you {role_name}. Sign in again to use your new access."
        cta = "Sign in"
    else:
        subject = f"[SeaWind] You are invited to SeaWind Task Management as {role_name}"
        body = f"The administrator invited you to join as {role_name}. Create your account with this email address ({email}) and your role is set up automatically."
        cta = "Create your account"
    title = subject.removeprefix("[SeaWind] ")
    text, html = email_bodies(title, body, link, False, cta)
    return subject, text, html
