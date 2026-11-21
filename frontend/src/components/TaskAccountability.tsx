import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, Select } from "@/components/ui";
import { DECISION_LABEL, EscalationBadge, fmtDateTime, fmtDay, WHY, type ExtensionReq, type Task } from "@/components/task-ui";
import { api } from "@/lib/api";

const area = "block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200";
const todayStr = () => new Date().toISOString().slice(0, 10);

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <Card className="mb-4 p-4"><h2 className="mb-3 text-sm font-semibold">{title}</h2>{children}</Card>;
}
const Buttons = ({ cta, onClose, danger, disabled }: { cta: string; onClose: () => void; danger?: boolean; disabled?: boolean }) => (
  <div className="flex items-end gap-2"><Button type="submit" variant={danger ? "danger" : "primary"} disabled={disabled}>{cta}</Button><Button type="button" variant="outline" onClick={onClose}>Cancel</Button></div>
);

// ------------------------------------------------------------------ overdue banner + the explanation gate

/** Red banner on an overdue task. For the assignee it opens the gate; for everyone else it is information. */
export function OverdueBanner({ t, mine, onExplain }: { t: Task; mine: boolean; onExplain: () => void }) {
  const d = t.delay;
  if (!d?.overdue) return null;
  return (
    <div role="alert" className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
      <div className="min-w-0 flex-1">
        {mine ? (
          d.required ? <><b>Your task deadline has passed. Please provide a reason for the delay.</b> <span className="text-red-800">{d.why ? WHY[d.why] : ""}</span></>
                     : <>Your deadline has passed. Your explanation is with your manager; add an update whenever things change.</>
        ) : (
          d.required ? <><b>Overdue, and no valid explanation yet.</b> {t.assignee.full_name} must explain the delay.</>
                     : <><b>Overdue.</b> {d.awaiting_review ? "An explanation is waiting for a decision." : d.latest_decision ? `Latest decision: ${DECISION_LABEL[d.latest_decision]}.` : ""}</>
        )}
        {" "}<EscalationBadge level={d.escalation_level} />
      </div>
      {mine && <Button variant={d.required ? "danger" : "outline"} onClick={onExplain}>{d.required ? "Explain the delay" : "Add an update"}</Button>}
    </div>
  );
}

/** A blocking overlay: the assignee cannot work around the requirement. "Later" only hides it until they navigate again. */
export function DelayGate({ t, onSubmit, error, busy }: { t: Task; onSubmit: (b: Record<string, unknown>) => void; error: unknown; busy: boolean }) {
  const [later, setLater] = useState(false);
  if (later) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-slate-900/60 p-4" role="dialog" aria-modal="true" aria-label="Explain the delay">
      <Card className="my-8 w-full max-w-2xl p-6">
        <h2 className="text-lg font-semibold text-red-700">Your task deadline has passed</h2>
        <p className="mt-1 text-sm text-slate-600"><b>{t.task_no} · {t.title}</b> was due {fmtDay(t.due_at)}. Please tell your manager where things stand. {t.delay?.why ? WHY[t.delay.why] : ""}</p>
        <div className="mt-4"><ExplainForm t={t} onSubmit={onSubmit} onClose={() => setLater(true)} closeLabel="Later" error={error} busy={busy} /></div>
        <p className="mt-3 text-xs text-slate-500">This cannot be dismissed for good: it returns every time you open the task until an explanation is submitted.</p>
      </Card>
    </div>
  );
}

export function ExplainForm({ t, onSubmit, onClose, closeLabel = "Cancel", error, busy }: { t: Task; onSubmit: (b: Record<string, unknown>) => void; onClose: () => void; closeLabel?: string; error: unknown; busy: boolean }) {
  const [f, setF] = useState({ reason: "", progress_pct: String(t.progress_pct), work_completed: "", remaining_work: "", blockers: "", expected_date: "", expected_time: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit({ reason: f.reason, progress_pct: Number(f.progress_pct), work_completed: f.work_completed, remaining_work: f.remaining_work, blockers: f.blockers || null, expected_date: f.expected_date, expected_time: f.expected_time || null }); }}
      className="grid gap-3 sm:grid-cols-2"
    >
      <div className="sm:col-span-2"><Field label="Reason for the delay"><textarea required minLength={5} rows={2} value={f.reason} onChange={set("reason")} className={area} /></Field></div>
      <Field label={`Current progress: ${f.progress_pct}%`}><input type="range" min={0} max={100} step={5} value={f.progress_pct} onChange={set("progress_pct")} className="w-full" /></Field>
      <Field label="Expected completion date"><Input required type="date" min={todayStr()} value={f.expected_date} onChange={set("expected_date")} /></Field>
      <div className="sm:col-span-2"><Field label="Work completed so far"><textarea required minLength={5} rows={2} value={f.work_completed} onChange={set("work_completed")} className={area} /></Field></div>
      <div className="sm:col-span-2"><Field label="Remaining work"><textarea required minLength={3} rows={2} value={f.remaining_work} onChange={set("remaining_work")} className={area} /></Field></div>
      <div className="sm:col-span-2"><Field label="Blockers or issues (optional)"><Input value={f.blockers} onChange={set("blockers")} /></Field></div>
      <div className="sm:col-span-2"><ErrorNote error={error} /></div>
      <Buttons cta="Submit explanation" onClose={onClose} disabled={busy} />
      {closeLabel !== "Cancel" && <span className="sr-only">{closeLabel}</span>}
    </form>
  );
}

export function ExplainPanel(props: { t: Task; onSubmit: (b: Record<string, unknown>) => void; onClose: () => void; error: unknown; busy: boolean }) {
  return <Panel title="Explain the delay (or send an update)"><ExplainForm {...props} /></Panel>;
}

// ------------------------------------------------------------------ deadline card (original, current, extensions, history, requests)

export function DeadlineCard({ t, tz, onChange, onRequest, canChange, canRequest, canDecide }: {
  t: Task; tz?: string; onChange: () => void; onRequest: () => void; canChange: boolean; canRequest: boolean; canDecide: boolean;
}) {
  const [open, setOpen] = useState(false);
  const dl = t.deadline!;
  const pending = dl.requests.filter((r) => r.status === "pending");
  return (
    <Card className="p-4 text-sm">
      <h2 className="text-sm font-semibold">Deadline</h2>
      <dl className="mt-3 space-y-3">
        <div><dt className="text-xs text-slate-500">Current deadline</dt><dd className={t.is_overdue ? "font-semibold text-red-600" : "font-medium"}>{fmtDay(dl.due_at, tz)}</dd></div>
        <div><dt className="text-xs text-slate-500">Original deadline</dt><dd>{fmtDay(dl.original_due_at, tz)}</dd></div>
        <div className="flex justify-between"><dt className="text-slate-500">Extensions</dt><dd className={dl.extension_count >= 3 ? "font-semibold text-orange-600" : ""}>{dl.extension_count}</dd></div>
        {t.completed_at && <div><dt className="text-xs text-slate-500">Completed</dt><dd>{fmtDateTime(t.completed_at, tz)}</dd></div>}
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        {canChange && <Button variant="outline" className="py-1" onClick={onChange}>Change deadline</Button>}
        {canRequest && <Button variant="outline" className="py-1" onClick={onRequest}>Request more time</Button>}
        {dl.history.length > 1 && <Button variant="ghost" className="py-1" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"} history ({dl.history.length - 1})</Button>}
      </div>
      {open && (
        <ol className="mt-3 space-y-3 border-l border-slate-200 pl-3">
          {dl.history.map((h) => (
            <li key={h.version} className="text-xs">
              <div className="font-medium">{h.type === "initial" ? "Set at creation" : h.type === "extension" ? "Extended" : "Shortened"}: {fmtDay(h.new_due_at, tz)}</div>
              {h.previous_due_at && <div className="text-slate-500">from {fmtDay(h.previous_due_at, tz)}</div>}
              {h.reason && h.type !== "initial" && <div className="text-slate-600">“{h.reason}”</div>}
              <div className="text-slate-400">{h.changed_by} · {fmtDay(h.at, tz)}</div>
            </li>
          ))}
        </ol>
      )}
      {dl.requests.length > 0 && (
        <div className="mt-4 space-y-2 border-t border-slate-100 pt-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Extension requests</div>
          {dl.requests.slice(0, 3).map((r) => <RequestRow key={r.id} r={r} tz={tz} canDecide={canDecide && r.status === "pending"} />)}
          {pending.length === 0 && dl.requests.length > 3 && <p className="text-xs text-slate-400">Older requests are in the activity trail.</p>}
        </div>
      )}
    </Card>
  );
}

export function RequestRow({ r, tz, canDecide }: { r: ExtensionReq; tz?: string; canDecide: boolean }) {
  const qc = useQueryClient();
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [declining, setDeclining] = useState(false);
  const done = () => { for (const k of ["task", "tasks", "extension-requests"]) qc.invalidateQueries({ queryKey: [k] }); };
  const m = useMutation({ mutationFn: (b: Record<string, unknown>) => api(`/extension-requests/${r.id}/decision`, { body: b }), onSuccess: done });
  return (
    <div className="rounded-lg bg-slate-50 p-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span>Asked for <b>{fmtDay(r.requested_due_at, tz)}</b></span>
        <Badge tone={r.status === "approved" ? "green" : r.status === "rejected" ? "red" : "orange"}>{r.status}</Badge>
      </div>
      <div className="text-slate-600">“{r.reason}”</div>
      {r.decision_note && <div className="text-slate-500">Note: {r.decision_note}</div>}
      {canDecide && (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Input type="date" min={todayStr()} className="max-w-36 py-1 text-xs" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Approve a different date (optional)" />
            <Button className="py-1" onClick={() => m.mutate({ decision: "approve", due_date: date || null })} disabled={m.isPending}>Approve{date ? " this date" : ""}</Button>
            <Button variant="outline" className="py-1" onClick={() => setDeclining(!declining)}>Decline</Button>
          </div>
          {declining && (
            <div className="flex gap-2"><Input className="py-1 text-xs" placeholder="Why? (required)" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button variant="danger" className="py-1" disabled={note.trim().length < 3} onClick={() => m.mutate({ decision: "reject", note })}>Send</Button></div>
          )}
          <ErrorNote error={m.error} />
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ deadline / extension panels

export function ChangeDeadlinePanel({ t, onSave, onClose }: { t: Task; onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [f, setF] = useState({ due_date: "", reason: "" });
  return (
    <Panel title="Change the deadline (the original deadline is always kept)">
      <p className="mb-3 text-xs text-slate-500">Current deadline: {fmtDay(t.due_at)}. The assignee and everyone above them can see who changed it and why.</p>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ due_date: f.due_date, reason: f.reason }); }} className="grid gap-3 sm:grid-cols-2">
        <Field label="New date"><Input required type="date" min={todayStr()} value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Reason (required, at least 10 characters)"><Input required minLength={10} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field></div>
        <Buttons cta="Change deadline" onClose={onClose} />
      </form>
    </Panel>
  );
}

export function RequestExtensionPanel({ t, onSave, onClose }: { t: Task; onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [f, setF] = useState({ due_date: "", reason: "" });
  return (
    <Panel title="Ask for more time">
      <p className="mb-3 text-xs text-slate-500">You cannot change the deadline yourself. Your manager will approve or decline. Current deadline: {fmtDay(t.due_at)}.</p>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ due_date: f.due_date, reason: f.reason }); }} className="grid gap-3 sm:grid-cols-2">
        <Field label="Requested date"><Input required type="date" min={todayStr()} value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Why do you need more time? (at least 10 characters)"><Input required minLength={10} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field></div>
        <Buttons cta="Send request" onClose={onClose} />
      </form>
    </Panel>
  );
}

// ------------------------------------------------------------------ explanation history + manager decision

export function DelaySection({ t, tz, canReview, onReview }: { t: Task; tz?: string; canReview: boolean; onReview: () => void }) {
  const items = t.delay?.items ?? [];
  if (items.length === 0) return null;
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Delay explanations</h2>
        {canReview && <Button className="py-1" onClick={onReview}>Decide on the latest</Button>}
      </div>
      <p className="text-xs text-slate-500">Every explanation is kept: they cannot be edited or deleted. A reason goes to the Department Head / Manager first; the CEO and Owner see it only after it is approved.</p>
      <ul className="mt-3 space-y-3 text-sm">
        {items.map((e) => (
          <li key={e.id} className="rounded-lg border border-slate-200 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">{e.kind === "initial" ? "Explanation" : "Update"} · deadline v{e.deadline_version}</span>
              <span className="text-xs text-slate-500">{fmtDateTime(e.at, tz)}</span>
            </div>
            <p className="mt-1 text-slate-800">{e.reason}</p>
            <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs text-slate-600 sm:grid-cols-2">
              <div><dt className="inline text-slate-400">Progress: </dt><dd className="inline">{e.progress_pct}%</dd></div>
              <div><dt className="inline text-slate-400">Expected: </dt><dd className="inline">{fmtDay(e.expected_completion_at, tz)}</dd></div>
              <div className="sm:col-span-2"><dt className="inline text-slate-400">Done: </dt><dd className="inline">{e.work_completed}</dd></div>
              <div className="sm:col-span-2"><dt className="inline text-slate-400">Remaining: </dt><dd className="inline">{e.remaining_work}</dd></div>
              {e.blockers && <div className="sm:col-span-2"><dt className="inline text-slate-400">Blockers: </dt><dd className="inline">{e.blockers}</dd></div>}
            </dl>
            {e.reviews.map((r, i) => (
              <p key={i} className="mt-2 rounded bg-slate-50 px-2 py-1 text-xs"><b>{DECISION_LABEL[r.decision] ?? r.decision}</b> by {r.by}{r.comment ? `: ${r.comment}` : ""} <span className="text-slate-400">· {fmtDay(r.at, tz)}</span></p>
            ))}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function ReviewDelayPanel({ onSave, onClose }: { onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [decision, setDecision] = useState("accepted");
  const [comment, setComment] = useState("");
  const [date, setDate] = useState("");
  const needsComment = decision === "clarification_requested" || decision === "rejected";
  return (
    <Panel title="Decide on the explanation">
      <p className="mb-3 text-xs text-slate-500">Accepting an explanation does not complete the task; it stays open until the work is done.</p>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ decision, comment: comment || null, due_date: decision === "revised_deadline_approved" ? date : null }); }} className="grid gap-3 sm:grid-cols-2">
        <Field label="Decision">
          <Select value={decision} onChange={(e) => setDecision(e.target.value)}>
            <option value="accepted">Accept the explanation</option>
            <option value="clarification_requested">Ask for more information</option>
            <option value="rejected">Do not accept</option>
            <option value="revised_deadline_approved">Approve a revised deadline</option>
            <option value="escalated">Escalate</option>
          </Select>
        </Field>
        {decision === "revised_deadline_approved" && <Field label="Revised deadline"><Input required type="date" min={todayStr()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>}
        <div className="sm:col-span-2"><Field label={needsComment ? "What do you need from the employee? (required)" : "Comment (optional)"}><Input required={needsComment} value={comment} onChange={(e) => setComment(e.target.value)} /></Field></div>
        <Buttons cta="Record decision" danger={decision === "rejected"} onClose={onClose} />
      </form>
    </Panel>
  );
}
