from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import PK, Base, UTCDateTime


class OutboxEvent(Base):
    """Something that happened. Written in the SAME transaction as the action, so a notification can never be
    lost (or sent for something that was rolled back). A relay turns each event into notifications."""

    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_status", "status", "id"), UniqueConstraint("dedupe_key", name="uq_outbox_dedupe"))

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60))
    task_id: Mapped[int | None] = mapped_column(PK, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(PK, nullable=True)  # NULL = the system
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)  # natural key for scheduler events
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending / done / skipped / failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class NotificationRule(Base):
    """WHO is told about WHAT. Recipients are described as relations ('the assignee', 'the assignee's manager',
    'everyone with the CEO role'), never as names, so they follow the hierarchy as it changes."""

    __tablename__ = "notification_rules"
    __table_args__ = (Index("ix_nr_event", "event_type", "enabled"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60))
    selector: Mapped[str] = mapped_column(String(60))  # ASSIGNEE, ASSIGNER, ACTOR, DIRECT_MANAGER, ANCESTOR_ROLE:manager, ROLE:ceo ...
    channels: Mapped[str] = mapped_column(String(20), default="in_app")  # in_app / email / in_app,email
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)  # people cannot mute mandatory notices
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)  # urgent emails ignore the working-hours window
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    condition_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # e.g. {"assigner_role": ["owner"]}
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60), primary_key=True)
    channel: Mapped[str] = mapped_column(String(10), primary_key=True)  # in_app / email
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # One notification per person per event: duplicates are physically impossible.
        UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),
        Index("ix_notif_user", "user_id", "is_read", "created_at"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    task_id: Mapped[int | None] = mapped_column(PK, nullable=True)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)  # why this person got it, e.g. ["ASSIGNEE"]
    dedupe_key: Mapped[str] = mapped_column(String(160))
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class EmailLog(Base):
    """Every email, its state and every attempt's error. Retries use backoff; nothing is silently dropped."""

    __tablename__ = "email_logs"
    __table_args__ = (Index("ix_email_status", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    notification_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id"), nullable=True)
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str] = mapped_column(Text)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued / sent / failed / skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ReminderRule(Base):
    """When automatic reminders and escalations fire, relative to a deadline. Editable by the Admin."""

    __tablename__ = "reminder_rules"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # before / at_due / after_working_days
    minutes: Mapped[int] = mapped_column(Integer, default=0)  # for 'before': minutes ahead of the deadline
    working_days: Mapped[int] = mapped_column(Integer, default=0)  # for 'after_working_days'
    event_type: Mapped[str] = mapped_column(String(60))
    statuses: Mapped[str] = mapped_column(String(200))  # comma-separated task statuses that get this reminder
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ReminderLog(Base):
    """UNIQUE per task + rule + deadline version + assignee: insert-before-notify makes every reminder exactly-once,
    even if the scanner runs twice or in parallel. A new deadline version starts a fresh schedule."""

    __tablename__ = "reminder_log"
    __table_args__ = (UniqueConstraint("task_id", "rule_id", "deadline_version", "assignee_id", name="uq_reminder_once"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    rule_id: Mapped[int] = mapped_column(ForeignKey("reminder_rules.id"))
    deadline_version: Mapped[int] = mapped_column(Integer)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    fired_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)


class JobFailure(Base):
    """Dead letters for the Admin: a background step that failed, with the error."""

    __tablename__ = "job_failures"

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    job: Mapped[str] = mapped_column(String(60))
    error: Mapped[str] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
