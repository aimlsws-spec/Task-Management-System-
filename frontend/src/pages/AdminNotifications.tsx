import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorNote, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/components/task-ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Rule = { id: number; event_type: string; label: string; selector: string; channels: string; mandatory: boolean; urgent: boolean; enabled: boolean; condition: Record<string, unknown> | null };
type Reminder = { id: number; code: string; kind: string; minutes: number; working_days: number; event_type: string; statuses: string[]; enabled: boolean };
type Mail = { id: number; to: string; subject: string; status: string; attempts: number; urgent: boolean; error: string | null; backend: string | null; created_at: string; sent_at: string | null };
type Status = { scheduler: { last_tick_at: string } | null; scheduler_running: boolean; scheduler_age_seconds: number | null; email_backend: string; smtp_configured: boolean; app_base_url: string; email_links_are_local: boolean; pending_events: number; queued_emails: number; failed_emails: number; failed_events: number };
type Failure = { id: number; job: string; error: string; created_at: string };

const SELECTOR: Record<string, string> = {
  ASSIGNEE: "the assignee", ASSIGNER: "who assigned it", ACTOR: "whoever did it (confirmation)", DIRECT_MANAGER: "the assignee's line manager",
  DEPARTMENT_HEAD: "the department head", PREVIOUS_ASSIGNEE: "the previous assignee", MANAGER_CHAIN: "everyone above",
};
const who = (s: string) => SELECTOR[s] ?? (s.startsWith("ROLE:") ? `everyone with the ${s.slice(5).toUpperCase()} role` : s.startsWith("ANCESTOR_ROLE:") ? `the ${s.slice(14)} above the assignee` : s);

export function AdminNotifications() {
  const [tab, setTab] = useState<"jobs" | "rules" | "timing" | "email">("jobs");
  const t = (id: typeof tab, label: string) => (
    <button onClick={() => setTab(id)} className={cn("rounded-lg px-3 py-1.5 text-sm font-medium", tab === id ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100")}>{label}</button>
  );
  return (
    <>
      <PageHeader title="Notifications & background jobs" subtitle="Who is told about what, when reminders fire, and whether email and the scheduler are healthy." />
      <div className="mb-4 flex flex-wrap gap-1">{t("jobs", "Health & jobs")}{t("rules", "Who is notified")}{t("timing", "Reminder timing")}{t("email", "Email log")}</div>
      {tab === "jobs" && <Jobs />}{tab === "rules" && <Rules />}{tab === "timing" && <Timing />}{tab === "email" && <EmailLog />}
    </>
  );
}

function Jobs() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["admin", "jobs", "status"], queryFn: () => api<Status>("/admin/jobs/status"), refetchInterval: 10_000 });
  const fails = useQuery({ queryKey: ["admin", "jobs", "failures"], queryFn: () => api<Failure[]>("/admin/jobs/failures") });
  const run = useMutation({ mutationFn: () => api("/admin/jobs/run-now", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin"] }) });
  const s = status.data;
  if (!s) return <Spinner />;
  const stat = (label: string, value: number | string, bad = false) => <Card className="p-4"><div className="text-xs text-slate-500">{label}</div><div className={cn("text-xl font-semibold", bad && "text-red-600")}>{value}</div></Card>;
  const lastTick = s.scheduler?.last_tick_at;
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {stat("Scheduler (cron)", s.scheduler_running ? "Running" : lastTick ? "Stopped" : "Never ran", !s.scheduler_running)}
        {stat("Email", s.email_backend === "smtp" ? (s.smtp_configured ? "SMTP" : "SMTP: not configured") : "Log only (dev)", s.email_backend === "smtp" && !s.smtp_configured)}
        {stat("Events waiting", s.pending_events)}
        {stat("Emails queued / failed", `${s.queued_emails} / ${s.failed_emails}`, s.failed_emails > 0)}
      </div>
      <Card className="p-4 text-sm">
        <p>Last pass: <b>{lastTick ? fmtDateTime(lastTick) : "never"}</b>. {!s.scheduler_running && "No pass in the last 3 minutes: check that the cPanel cron job (every minute, app/jobs/run_once.py) is set up and see logs/scheduler.log."}</p>
        {(s.email_backend !== "smtp" || !s.smtp_configured) && (
          <p role="status" className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-amber-900">
            <b>No email is leaving the server yet.</b> In-app notifications work, but emails (invitations, new sign-ups, tasks, reminders) are only written to the server log.
            To send real email, fill in <code>TMS_EMAIL_BACKEND=smtp</code>, <code>TMS_SMTP_HOST</code>, <code>TMS_SMTP_PORT</code>, <code>TMS_SMTP_USER</code>, <code>TMS_SMTP_PASSWORD</code> and <code>TMS_EMAIL_FROM</code> in <code>backend/.env</code>, then restart the app. Queued emails are sent afterwards.
          </p>
        )}
        <div className="mt-3 flex items-center gap-3"><Button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? "Running…" : "Run a pass now"}</Button><ErrorNote error={run.error} /></div>
      </Card>
      <Card className="overflow-x-auto">
        <div className="p-4 pb-0"><h2 className="text-sm font-semibold">Recent failures <Badge tone={fails.data?.length ? "red" : "grey"}>{fails.data?.length ?? 0}</Badge></h2></div>
        <table className="mt-2 w-full text-left text-sm"><tbody>
          {fails.data?.map((f) => <tr key={f.id} className="border-t border-slate-100"><td className="whitespace-nowrap p-3 text-xs text-slate-500">{fmtDateTime(f.created_at)}</td><td className="p-3 font-medium">{f.job}</td><td className="p-3 text-xs text-red-700">{f.error}</td></tr>)}
          {fails.data?.length === 0 && <tr><td className="p-6 text-center text-slate-500">No failures.</td></tr>}
        </tbody></table>
      </Card>
    </div>
  );
}

function Rules() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "rules"], queryFn: () => api<Rule[]>("/admin/notification-rules") });
  const edit = useMutation({ mutationFn: (v: { id: number; body: Record<string, unknown> }) => api(`/admin/notification-rules/${v.id}`, { method: "PATCH", body: v.body }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "rules"] }) });
  if (q.isLoading) return <Spinner />;
  let last = "";
  return (
    <Card className="overflow-x-auto">
      <p className="p-4 pb-0 text-sm text-slate-600">Each row says who is told when something happens. People are described by their relationship (the assignee, their manager, the department head), never by name, so this follows the hierarchy as it changes. <b>Mandatory</b> notices cannot be muted by people; <b>urgent</b> emails are sent outside working hours too.</p>
      <table className="mt-3 w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500"><tr><th className="p-3">Event</th><th className="p-3">Who is told</th><th className="p-3">Channels</th><th className="p-3 text-center">Mandatory</th><th className="p-3 text-center">Urgent</th><th className="p-3 text-center">On</th></tr></thead>
        <tbody>
          {q.data?.map((r) => {
            const first = r.event_type !== last; last = r.event_type;
            return (
              <tr key={r.id} className={cn("border-slate-100", first ? "border-t-2 border-t-slate-200" : "border-t", !r.enabled && "opacity-60")}>
                <td className="p-3 font-medium">{first ? r.label : ""}</td>
                <td className="p-3">{who(r.selector)}{r.condition && <span className="ml-1 text-xs text-slate-400">· only when {Object.entries(r.condition).map(([k, v]) => `${k.replace("_", " ")} is ${(v as string[]).join("/")}`).join(", ")}</span>}</td>
                <td className="p-3"><Select className="max-w-32 py-1 text-xs" value={r.channels} onChange={(e) => edit.mutate({ id: r.id, body: { channels: e.target.value } })}><option value="in_app">In app</option><option value="email">Email</option><option value="in_app,email">App + email</option></Select></td>
                {(["mandatory", "urgent", "enabled"] as const).map((k) => <td key={k} className="p-3 text-center"><input type="checkbox" aria-label={`${r.label} ${who(r.selector)} ${k}`} checked={r[k]} onChange={(e) => edit.mutate({ id: r.id, body: { [k]: e.target.checked } })} /></td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="p-3"><ErrorNote error={edit.error} /></div>
    </Card>
  );
}

function Timing() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "timing"], queryFn: () => api<Reminder[]>("/admin/reminder-rules") });
  const edit = useMutation({ mutationFn: (v: { id: number; body: Record<string, unknown> }) => api(`/admin/reminder-rules/${v.id}`, { method: "PATCH", body: v.body }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "timing"] }) });
  if (q.isLoading) return <Spinner />;
  const when = (r: Reminder) => (r.kind === "before" ? `${r.minutes / 60 >= 1 ? `${r.minutes / 60} h` : `${r.minutes} min`} before the deadline` : r.kind === "at_due" ? "when the deadline passes" : `${r.working_days} working day${r.working_days > 1 ? "s" : ""} after the deadline`);
  return (
    <Card className="overflow-x-auto">
      <p className="p-4 pb-0 text-sm text-slate-600">Reminders are never sent for tasks on hold, waiting for review, cancelled or completed, and never for a deadline that has since changed. Working days skip Sundays, off Saturdays and holidays.</p>
      <table className="mt-3 w-full text-left text-sm"><tbody>
        {q.data?.map((r) => (
          <tr key={r.id} className="border-t border-slate-100">
            <td className="p-3 font-medium">{when(r)}<div className="text-xs font-normal text-slate-400">{r.code}</div></td>
            <td className="p-3">
              {r.kind === "before" && <label className="text-xs text-slate-500">Minutes ahead <Input type="number" min={0} max={10080} className="mt-1 max-w-28 py-1" defaultValue={r.minutes} onBlur={(e) => Number(e.target.value) !== r.minutes && edit.mutate({ id: r.id, body: { minutes: Number(e.target.value) } })} /></label>}
              {r.kind === "after_working_days" && <label className="text-xs text-slate-500">Working days <Input type="number" min={1} max={60} className="mt-1 max-w-28 py-1" defaultValue={r.working_days} onBlur={(e) => Number(e.target.value) !== r.working_days && edit.mutate({ id: r.id, body: { working_days: Number(e.target.value) } })} /></label>}
            </td>
            <td className="p-3 text-center"><label className="text-xs text-slate-500">On <input type="checkbox" className="ml-1" checked={r.enabled} onChange={(e) => edit.mutate({ id: r.id, body: { enabled: e.target.checked } })} /></label></td>
          </tr>
        ))}
      </tbody></table>
      <div className="p-3"><ErrorNote error={edit.error} /></div>
    </Card>
  );
}

function EmailLog() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["admin", "email", status], queryFn: () => api<{ items: Mail[]; total: number }>("/admin/email-logs", { params: { status } }) });
  const retry = useMutation({ mutationFn: (id: number) => api(`/admin/email-logs/${id}/retry`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin"] }) });
  return (
    <Card className="overflow-x-auto">
      <div className="flex items-center gap-3 p-4 pb-0"><Select className="max-w-40" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option value="queued">Queued</option><option value="sent">Sent</option><option value="failed">Failed</option><option value="skipped">Skipped</option></Select><span className="text-sm text-slate-500">{q.data?.total ?? 0} emails</span></div>
      <table className="mt-2 w-full text-left text-sm"><tbody>
        {q.data?.items.map((m) => (
          <tr key={m.id} className="border-t border-slate-100">
            <td className="p-3"><div className="font-medium">{m.subject}</div><div className="text-xs text-slate-500">to {m.to} · {fmtDateTime(m.created_at)}{m.urgent && " · urgent"}</div>{m.error && <div className="text-xs text-red-700">{m.error}</div>}</td>
            <td className="p-3"><Badge tone={m.status === "sent" ? "green" : m.status === "failed" ? "red" : m.status === "queued" ? "orange" : "grey"}>{m.status}</Badge><div className="text-xs text-slate-400">{m.attempts} attempt(s)</div></td>
            <td className="p-3 text-right">{(m.status === "failed" || m.status === "skipped") && <Button variant="outline" className="py-1" onClick={() => retry.mutate(m.id)}>Retry</Button>}</td>
          </tr>
        ))}
        {q.data?.items.length === 0 && <tr><td className="p-6 text-center text-slate-500">No emails.</td></tr>}
      </tbody></table>
      <div className="p-3"><ErrorNote error={retry.error} /></div>
    </Card>
  );
}
