import { AlertOctagon, AlertTriangle, ArrowDown, Minus } from "lucide-react";
import { Badge } from "@/components/ui";

export type Person = { id: number; full_name: string; job_title: string | null; department_id: number; employee_code: string };
export type Task = {
  id: number; task_no: string; title: string; status: string; priority: string; assignee: Person; assigned_by: Person;
  department_id: number; company_id?: number; project_id: number | null; category_id: number | null; type_id: number | null;
  assigned_at: string; start_date: string | null; original_due_at: string; due_at: string; extension_count: number;
  estimated_hours: number; progress_pct: number; is_overdue: boolean; requires_review: boolean; version: number;
  acknowledged_at: string | null; completed_at: string | null; review_stage?: "qa" | "head" | "leadership" | null;
  head?: Person | null; sub_head?: Person | null; heads?: Person[]; qa?: Person | null; qa_members?: Person[];
  assignment_history?: { id: number; assignee?: Person | null; assigned_by?: Person | null; assigned_at: string; unassigned_at?: string | null; reason?: string | null }[];
  // detail only
  description?: string; instructions?: string | null; deadline_version?: number; cancel_reason?: string | null;
  project?: string | null; category?: string | null; type?: string | null; allowed_actions?: string[];
  status_history?: { from: string | null; to: string; reason: string | null; at: string }[];
  attachments?: { id: number; name: string; size_bytes: number; mime_type: string; at: string }[];
  timer_running?: boolean; time?: TimeSummary; revert_count?: number; verified_at?: string | null; submitted_at?: string | null;
  updates?: { progress_pct: number; note: string; at: string }[];
  assurances?: { attempt: number; summary: string; tested: boolean; test_notes: string | null; evidence_url: string | null; no_time_reason: string | null; at: string }[];
  reverts?: { attempt: number; reason_code: string; reason: string; found_by: string | null; bug_sheet_url?: string | null; at: string }[];
  explanation_required?: boolean; escalation_level?: number;
  deadline?: DeadlineBlock; delay?: DelayState;
  accountable_head?: { id: number | null; full_name: string | null } | null;
  ownership?: { employee_id: number; full_name: string; note: string | null; at: string }[];
  blockers?: import("@/components/Collab").Blocker[]; open_blockers?: number;
};
export type HistoryRow = { version: number; type: string; previous_due_at: string | null; new_due_at: string; changed_by: string | null; reason: string | null; at: string };
export type ExtensionReq = {
  id: number; task_id: number; task_no: string; title: string; requested_by: string; current_due_at: string; requested_due_at: string;
  reason: string; status: string; decided_by: string | null; decision_note: string | null; approved_due_at: string | null; assignee?: string;
};
export type DeadlineBlock = { original_due_at: string; due_at: string; version: number; extension_count: number; history: HistoryRow[]; requests: ExtensionReq[] };
export type Explanation = {
  id: number; deadline_version: number; kind: string; reason: string; progress_pct: number; work_completed: string; remaining_work: string;
  blockers: string | null; expected_completion_at: string; at: string;
  reviews: { decision: string; comment: string | null; by: string | null; at: string }[];
};
export type DelayState = {
  overdue: boolean; required: boolean; why: null | "none_submitted" | "needs_update" | "stale"; explanations: number;
  latest_decision: string | null; awaiting_review: boolean; escalation_level: number; items: Explanation[];
};
export type DelayQueue = {
  missing: { task_id: number; task_no: string; title: string; assignee: string; priority: string; due_at: string; extension_count: number; escalation_level: number; why: string }[];
  awaiting: { task_id: number; task_no: string; title: string; assignee: string; priority: string; due_at: string; extension_count: number; escalation_level: number; explanation: Explanation }[];
};
export type Session = {
  id: number; task_id: number; employee_id: number; started_at: string; ended_at: string | null; seconds: number;
  source: string; end_reason: string | null; confirmed: boolean; running: boolean; note: string | null;
  task?: { id: number; task_no: string; title: string }; employee?: { id: number; full_name: string };
  suggested_end?: string;
};
export type TimeSummary = {
  estimated_seconds: number; active_seconds: number; provisional_seconds: number; remaining_seconds: number;
  elapsed_seconds: number; assign_to_start_seconds: number | null; blocked_seconds?: number; running: boolean; sessions: Session[];
};
export type Correction = {
  id: number; task_id: number; employee_id: number; kind: string; new_started_at: string; new_ended_at: string;
  reason: string; status: string; decision_note: string | null; created_at: string; employee?: string;
  task?: { task_no: string; title: string }; can_decide?: boolean;
};
export type ActiveTimer = {
  active: null | {
    time_log_id: number; task: { id: number; task_no: string; title: string }; started_at: string; elapsed_seconds: number;
    continuous_since: string; cap_at: string; checkin: null | { kind: string; at: string };
  };
  server_time: string;
};

export function fmtDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
}
export function fmtClock(seconds: number) {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}
export type TaskPage = { items: Task[]; total: number; page: number; page_size: number };
export type Workload = {
  employee_id: number; full_name: string; job_title: string | null; department_id: number; department: string | null;
  on_leave: boolean; is_me: boolean; open_tasks: number; overdue_tasks: number; due_next_7_days: number;
  by_status: Record<string, number>; by_priority: Record<"critical" | "high" | "medium" | "low", number>;
  open_estimated_hours: number; open_remaining_hours: number; next7_estimated_hours: number; capacity_hours_next_7_days: number; load_pct: number;
  level: "normal" | "high" | "overloaded";
};

const STATUS: Record<string, { label: string; tone: "grey" | "blue" | "green" | "red" | "orange" | "purple" | "indigo" }> = {
  assigned: { label: "Assigned", tone: "grey" },
  acknowledged: { label: "Acknowledged", tone: "grey" },
  in_progress: { label: "In progress", tone: "blue" },
  on_hold: { label: "On hold", tone: "grey" },
  blocked: { label: "Blocked", tone: "orange" },
  under_review: { label: "Under review", tone: "purple" },
  completed: { label: "Completed", tone: "green" },
  reopened: { label: "Reopened", tone: "indigo" },
  cancelled: { label: "Cancelled", tone: "grey" },
};
export const STATUS_OPTIONS = Object.entries(STATUS).map(([value, v]) => ({ value, label: v.label }));
export const statusLabel = (s: string) => STATUS[s]?.label ?? s;

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, tone: "grey" as const };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

const PRIORITY = { critical: { tone: "red", label: "Critical" }, high: { tone: "orange", label: "High" }, medium: { tone: "blue", label: "Medium" }, low: { tone: "grey", label: "Low" } } as const;
export function PriorityChip({ priority }: { priority: string }) {
  const p = PRIORITY[priority as keyof typeof PRIORITY] ?? PRIORITY.medium;
  const Icon = priority === "critical" ? AlertOctagon : priority === "high" ? AlertTriangle : priority === "low" ? ArrowDown : Minus;
  return (
    <Badge tone={p.tone}>
      <span className="inline-flex items-center gap-1">
        <Icon className="h-3 w-3" />
        <span>{p.label}</span>
      </span>
    </Badge>
  );
}

export function LevelBadge({ level }: { level: Workload["level"] }) {
  return <Badge tone={level === "normal" ? "green" : level === "high" ? "orange" : "red"}>{level === "normal" ? "Normal" : level === "high" ? "High" : "Overloaded"}</Badge>;
}

export const OverdueBadge = () => <Badge tone="red">Overdue</Badge>;

/** Instants arrive as UTC ISO strings; show them in the signed-in user's timezone. */
export function fmtDateTime(iso: string | null | undefined, tz = "Asia/Kolkata") {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZone: tz }).format(new Date(iso));
}
export function fmtDay(iso: string | null | undefined, tz = "Asia/Kolkata") {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: tz }).format(new Date(iso));
}

export const ACTION_LABEL: Record<string, string> = {
  TASK_CREATED: "Task created and assigned",
  TASK_ACKNOWLEDGED: "Acknowledged by assignee",
  TASK_UPDATED: "Details edited",
  TASK_REASSIGNED: "Reassigned",
  TASK_PRIORITY_CHANGED: "Priority changed",
  TASK_CANCELLED: "Cancelled",
  TASK_DEADLINE_CHANGED: "Deadline changed",
  DELAY_EXPLANATION_SUBMITTED: "Delay explanation submitted",
  DELAY_REVIEWED: "Delay explanation reviewed",
  EXTENSION_REQUESTED: "Extension requested",
  EXTENSION_DECIDED: "Extension request decided",
  TIMER_STARTED: "Timer started",
  TIMER_PAUSED: "Timer paused",
  TIMER_STOPPED: "Timer stopped",
  TIMER_SWITCHED: "Switched to another task",
  TIMER_AUTO_CLOSED: "Timer closed automatically (forgotten)",
  TASK_PROGRESS: "Progress update",
  TASK_ON_HOLD: "Put on hold",
  TASK_RESUMED_FROM_HOLD: "Resumed from hold",
  TASK_COMPLETED: "Marked complete by assignee",
  TASK_SUBMITTED: "Submitted for review",
  TASK_REVIEW_APPROVED: "Review approved",
  TASK_REVIEW_REJECTED: "Review rejected",
  TASK_VERIFIED: "Verified",
  TASK_REVERTED: "Reverted: sent back",
  TIME_CORRECTION_REQUESTED: "Missing time requested",
  TIME_CORRECTION_APPROVED: "Missing time approved",
  TIME_CORRECTION_REJECTED: "Missing time rejected",
  TIME_LOG_ADJUSTED: "Time entry adjusted",
  TIME_LOG_CONFIRMED: "Auto-closed time confirmed",
  TASK_ATTACHMENT_ADDED: "File attached",
  BLOCKER_RAISED: "Blocker reported", BLOCKER_ACKNOWLEDGED: "Blocker acknowledged", BLOCKER_ASSIGNED: "Blocker assigned",
  BLOCKER_IN_PROGRESS: "Work started on blocker", BLOCKER_REPLIED: "Blocker reply", BLOCKER_RESOLVED: "Blocker resolved",
  BLOCKER_CLOSED: "Blocker closed", BLOCKER_REOPENED: "Blocker reopened", BLOCKER_ESCALATED: "Blocker escalated",
  COMMENT_ADDED: "Comment added", QUESTION_ASKED: "Question asked", COMMENT_EDITED: "Comment edited",
};

export function LoadBar({ pct }: { pct: number }) {
  const w = Math.min(100, Math.max(0, pct));
  const color = pct <= 80 ? "bg-green-500" : pct <= 100 ? "bg-orange-500" : "bg-red-500";
  return (
    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200" title={`${pct}% of the next 7 days' capacity`}>
      <div className={`h-full ${color}`} style={{ width: `${w}%` }} />
    </div>
  );
}

export function PriorityCounts({ c }: { c: Workload["by_priority"] }) {
  const cell = (n: number, cls: string, t: string) => (
    <span title={t} className={`inline-flex min-w-6 justify-center rounded px-1.5 py-0.5 text-xs font-semibold ${n ? cls : "bg-slate-50 text-slate-300"}`}>{n}</span>
  );
  return (
    <span className="inline-flex gap-1">
      {cell(c.critical, "bg-red-100 text-red-700", "Critical")}
      {cell(c.high, "bg-orange-100 text-orange-700", "High")}
      {cell(c.medium, "bg-blue-100 text-blue-700", "Medium")}
      {cell(c.low, "bg-slate-100 text-slate-600", "Low")}
    </span>
  );
}

export const WHY: Record<string, string> = {
  none_submitted: "The deadline has passed and no explanation has been given.",
  needs_update: "Your manager asked for more information, or did not accept the last explanation.",
  stale: "It has been several days since your last update and the task is still overdue.",
};
export const DECISION_LABEL: Record<string, string> = {
  accepted: "Accepted", clarification_requested: "More information requested", rejected: "Not accepted",
  revised_deadline_approved: "New deadline approved", escalated: "Escalated",
};
export function EscalationBadge({ level }: { level?: number }) {
  if (!level) return null;
  return <Badge tone={level >= 3 ? "red" : "orange"}>Escalation {level}</Badge>;
}
