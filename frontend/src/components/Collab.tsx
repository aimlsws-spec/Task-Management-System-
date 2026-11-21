import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, Select } from "@/components/ui";
import { fmtDateTime, fmtDuration, type Workload } from "@/components/task-ui";
import { api } from "@/lib/api";

export type BlockerEvent = { event: string; by: string | null; from: string | null; to: string | null; note: string | null; at: string };
export type Blocker = {
  id: number; task: { id: number; task_no: string; title: string; priority: string }; type: string; title: string; description: string;
  impact: string | null; blocks_work: boolean; expected_resolution: string | null; status: string; raised_by: string | null; owner: string | null;
  opened_at: string; resolved_at: string | null; closed_at: string | null; resolution_note: string | null; open_hours: number;
  escalated_to_leadership?: boolean;
  events?: BlockerEvent[]; actions: string[]; assignee?: string;
};
export type Comment = {
  id: number; parent_id: number | null; kind: string; body: string; author: string | null; author_user_id: number;
  mentions: { user_id: number; full_name: string }[]; edited: boolean; at: string;
};
type Mentionable = { user_id: number; full_name: string; job_title: string | null; why: string };

export const BLOCKER_TYPES = [["technical", "Technical problem"], ["dependency", "Waiting on another task or team"], ["information", "Missing information"], ["resource", "Missing resource"], ["access", "Access or permission"], ["other", "Other"]] as const;
const STATUS_LABEL: Record<string, string> = { open: "Open", acknowledged: "Acknowledged", in_progress: "In progress", resolved: "Resolved", closed: "Closed" };
const STATUS_TONE: Record<string, "red" | "orange" | "blue" | "green" | "grey"> = { open: "red", acknowledged: "orange", in_progress: "blue", resolved: "green", closed: "grey" };
const EVENT_LABEL: Record<string, string> = { created: "Reported", acknowledged: "Acknowledged", assigned: "Assigned", in_progress: "Work started", replied: "Reply", resolved: "Resolved", closed: "Closed", reopened: "Reopened", escalated: "Escalated" };
const textarea = "block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200";

export const BlockerStatus = ({ status }: { status: string }) => <Badge tone={STATUS_TONE[status] ?? "grey"}>{STATUS_LABEL[status] ?? status}</Badge>;

// ------------------------------------------------------------------ raise a blocker

export function RaiseBlockerPanel({ onSave, onClose, error, busy }: { onSave: (b: Record<string, unknown>) => void; onClose: () => void; error: unknown; busy: boolean }) {
  const [f, setF] = useState({ blocker_type: "technical", title: "", description: "", impact: "", expected_resolution: "", blocks_work: true });
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Card className="mb-4 p-4">
      <h2 className="mb-1 text-sm font-semibold">Report a blocker</h2>
      <p className="mb-3 text-xs text-slate-500">Your manager and department head are told straight away. If work cannot continue, the task becomes <b>Blocked</b>, your timer stops, and the waiting time is recorded separately from your working time.</p>
      <form
        onSubmit={(e) => { e.preventDefault(); onSave({ ...f, impact: f.impact || null, expected_resolution: f.expected_resolution || null }); }}
        className="grid gap-3 sm:grid-cols-2"
      >
        <Field label="What kind of problem?"><Select value={f.blocker_type} onChange={set("blocker_type")}>{BLOCKER_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        <Field label="Short title"><Input required minLength={3} value={f.title} onChange={set("title")} placeholder="e.g. API credentials missing" /></Field>
        <div className="sm:col-span-2"><Field label="What is happening?"><textarea required minLength={5} rows={3} value={f.description} onChange={set("description")} className={textarea} /></Field></div>
        <Field label="Impact (optional)"><Input value={f.impact} onChange={set("impact")} placeholder="What cannot be done because of it?" /></Field>
        <Field label="What do you need? (optional)"><Input value={f.expected_resolution} onChange={set("expected_resolution")} placeholder="e.g. credentials from the vendor" /></Field>
        <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={f.blocks_work} onChange={(e) => setF({ ...f, blocks_work: e.target.checked })} /> I cannot continue working until this is solved</label>
        <div className="sm:col-span-2"><ErrorNote error={error} /></div>
        <div className="flex gap-2"><Button type="submit" disabled={busy}>Report blocker</Button><Button type="button" variant="outline" onClick={onClose}>Cancel</Button></div>
      </form>
    </Card>
  );
}

// ------------------------------------------------------------------ one blocker with its actions and history

export function BlockerCard({ b, tz, onChanged, showTask }: { b: Blocker; tz?: string; onChanged: () => void; showTask?: boolean }) {
  const [mode, setMode] = useState<null | "resolve" | "reply" | "reopen" | "escalate" | "assign">(null);
  const [note, setNote] = useState("");
  const [owner, setOwner] = useState("");
  const [open, setOpen] = useState(false);
  const people = useQuery({ queryKey: ["workload"], queryFn: () => api<Workload[]>("/workload"), enabled: mode === "assign" });
  const run = useMutation({
    mutationFn: (v: { action: string; body?: unknown }) => api(`/blockers/${b.id}/${v.action}`, { method: "POST", body: v.body ?? {} }),
    onSuccess: () => { setMode(null); setNote(""); onChanged(); },
  });
  const has = (a: string) => b.actions.includes(a);
  const go = (action: string, body?: unknown) => run.mutate({ action, body });
  const needsNote = mode === "resolve" || mode === "reply" || mode === "reopen" || mode === "escalate";
  return (
    <li className="rounded-lg border border-slate-200 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <b>{b.title}</b><BlockerStatus status={b.status} />
        {b.blocks_work ? <Badge tone="orange">Stops work</Badge> : <Badge tone="grey">Work continues</Badge>}
        {b.escalated_to_leadership && <Badge tone="red">Escalated to Leadership</Badge>}
        <span className="text-xs text-slate-400">{b.open_hours}h {b.status === "resolved" || b.status === "closed" ? "to solve" : "open"}</span>
      </div>
      {showTask && <p className="mt-1 text-xs text-slate-500">{b.task.task_no} · {b.task.title}{b.assignee ? ` · ${b.assignee}` : ""}</p>}
      <p className="mt-1 whitespace-pre-wrap text-slate-700">{b.description}</p>
      <p className="mt-1 text-xs text-slate-500">
        Reported by {b.raised_by} · {fmtDateTime(b.opened_at, tz)}{b.owner ? ` · being solved by ${b.owner}` : ""}{b.impact ? ` · Impact: ${b.impact}` : ""}{b.expected_resolution ? ` · Needs: ${b.expected_resolution}` : ""}
      </p>
      {b.resolution_note && <p className="mt-1 rounded bg-green-50 px-2 py-1 text-xs text-green-900"><b>Resolution:</b> {b.resolution_note}</p>}
      <div className="mt-2 flex flex-wrap gap-2">
        {has("acknowledge") && <Button variant="outline" className="py-1" onClick={() => go("acknowledge")}>Acknowledge</Button>}
        {has("start") && <Button variant="outline" className="py-1" onClick={() => go("start")}>Start working on it</Button>}
        {has("assign") && <Button variant="outline" className="py-1" onClick={() => setMode("assign")}>Assign to someone</Button>}
        {has("resolve") && <Button className="py-1" onClick={() => setMode("resolve")}>Resolve</Button>}
        {has("reply") && <Button variant="outline" className="py-1" onClick={() => setMode("reply")}>Reply</Button>}
        {has("escalate") && <Button variant="danger" className="py-1" onClick={() => setMode("escalate")}>Escalate to CEO / Owner</Button>}
        {has("reopen") && <Button variant="outline" className="py-1" onClick={() => setMode("reopen")}>Still a problem: reopen</Button>}
        {has("close") && <Button variant="outline" className="py-1" onClick={() => go("close")}>{b.status === "resolved" ? "Confirm solved" : "Withdraw / close"}</Button>}
        {b.events && <Button variant="ghost" className="py-1" onClick={() => setOpen(!open)}>{open ? "Hide history" : `History (${b.events.length})`}</Button>}
      </div>
      {mode === "assign" && (
        <form className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); go("assign", { owner_employee_id: Number(owner), note: note || null }); }}>
          <Select required value={owner} onChange={(e) => setOwner(e.target.value)}><option value="">Who should solve it?</option>{people.data?.map((p) => <option key={p.employee_id} value={p.employee_id}>{p.full_name}</option>)}</Select>
          <Input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2"><Button type="submit" className="py-1">Assign</Button><Button type="button" variant="outline" className="py-1" onClick={() => setMode(null)}>Cancel</Button></div>
        </form>
      )}
      {needsNote && (
        <form className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto]" onSubmit={(e) => { e.preventDefault(); go(mode!, { note }); }}>
          <Input required minLength={2} autoFocus placeholder={mode === "resolve" ? "How was it solved?" : mode === "reopen" ? "Why is it still a problem?" : mode === "escalate" ? "Why does this need CEO / Owner attention?" : "Write a reply"} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2"><Button type="submit" className="py-1">{mode === "escalate" ? "Escalate now" : "Send"}</Button><Button type="button" variant="outline" className="py-1" onClick={() => setMode(null)}>Cancel</Button></div>
        </form>
      )}
      <ErrorNote error={run.error} />
      {open && b.events && (
        <ol className="mt-3 space-y-2 border-l border-slate-200 pl-3">
          {b.events.map((e, i) => (
            <li key={i} className="text-xs"><b>{EVENT_LABEL[e.event] ?? e.event}</b> · {e.by} · <span className="text-slate-400">{fmtDateTime(e.at, tz)}</span>{e.note && <div className="text-slate-600">{e.note}</div>}</li>
          ))}
        </ol>
      )}
    </li>
  );
}

export function BlockersSection({ blockers, tz, onChanged }: { blockers: Blocker[]; tz?: string; onChanged: () => void }) {
  if (blockers.length === 0) return null;
  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold">Blockers</h2>
      <p className="text-xs text-slate-500">Problems reported on this task and how they were solved. Waiting time is tracked apart from working time.</p>
      <ul className="mt-3 space-y-3">{blockers.map((b) => <BlockerCard key={b.id} b={b} tz={tz} onChanged={onChanged} />)}</ul>
    </Card>
  );
}

export function BlockedTimeRow({ seconds }: { seconds?: number }) {
  if (!seconds) return null;
  return <div className="flex justify-between"><dt className="text-slate-500">Blocked (waiting)</dt><dd className="font-medium text-orange-700">{fmtDuration(seconds)}</dd></div>;
}

// ------------------------------------------------------------------ discussion

export function Discussion({ taskId, tz, myUserId }: { taskId: number; tz?: string; myUserId?: number }) {
  const qc = useQueryClient();
  const comments = useQuery({ queryKey: ["task", String(taskId), "comments"], queryFn: () => api<Comment[]>(`/tasks/${taskId}/comments`) });
  const people = useQuery({ queryKey: ["task", String(taskId), "mentionable"], queryFn: () => api<Mentionable[]>(`/tasks/${taskId}/mentionable`) });
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("comment");
  const [mentions, setMentions] = useState<number[]>([]);
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [editing, setEditing] = useState<{ id: number; body: string } | null>(null);
  const done = () => { qc.invalidateQueries({ queryKey: ["task", String(taskId)] }); };
  const send = useMutation({
    mutationFn: () => api(`/tasks/${taskId}/comments`, { body: { kind, body, parent_id: replyTo?.id ?? null, mentions } }),
    onSuccess: () => { setBody(""); setMentions([]); setReplyTo(null); setKind("comment"); done(); },
  });
  const edit = useMutation({ mutationFn: () => api(`/comments/${editing!.id}`, { method: "PATCH", body: { body: editing!.body } }), onSuccess: () => { setEditing(null); done(); } });
  const list = comments.data ?? [];
  const top = list.filter((c) => !c.parent_id);
  const render = (c: Comment, nested = false) => (
    <li key={c.id} className={`rounded-lg border p-3 text-sm ${nested ? "ml-6 border-slate-100 bg-slate-50" : "border-slate-200"}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <b className="text-slate-800">{c.author}</b>
        {(c.kind === "question" || c.kind === "clarification") && <Badge tone="purple">{c.kind === "question" ? "Question" : "Clarification"}</Badge>}
        <span>{fmtDateTime(c.at, tz)}{c.edited ? " · edited" : ""}</span>
      </div>
      {editing?.id === c.id ? (
        <form className="mt-2 grid gap-2" onSubmit={(e) => { e.preventDefault(); edit.mutate(); }}>
          <textarea rows={2} className={textarea} value={editing.body} onChange={(e) => setEditing({ id: c.id, body: e.target.value })} />
          <ErrorNote error={edit.error} />
          <div className="flex gap-2"><Button type="submit" className="py-1">Save</Button><Button type="button" variant="outline" className="py-1" onClick={() => setEditing(null)}>Cancel</Button></div>
        </form>
      ) : <p className="mt-1 whitespace-pre-wrap text-slate-700">{c.body}</p>}
      {c.mentions.length > 0 && <p className="mt-1 text-xs text-indigo-700">{c.mentions.map((m) => `@${m.full_name}`).join(" ")}</p>}
      <div className="mt-1 flex gap-3 text-xs">
        {!nested && <button className="text-indigo-600 hover:underline" onClick={() => setReplyTo(c)}>Reply</button>}
        {c.author_user_id === myUserId && <button className="text-slate-500 hover:underline" onClick={() => setEditing({ id: c.id, body: c.body })}>Edit</button>}
      </div>
    </li>
  );
  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold">Discussion</h2>
      <p className="text-xs text-slate-500">Ask questions and clarify requirements here instead of in chat, so the answer stays with the task. Mention someone to notify them.</p>
      <ul className="mt-3 space-y-3">
        {top.length === 0 && <li className="text-sm text-slate-500">No comments yet.</li>}
        {top.map((c) => (
          <div key={c.id} className="space-y-2">{render(c)}{list.filter((r) => r.parent_id === c.id).map((r) => render(r, true))}</div>
        ))}
      </ul>
      <form className="mt-4 grid gap-2" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
        {replyTo && <p className="text-xs text-slate-500">Replying to <b>{replyTo.author}</b> <button type="button" className="text-indigo-600 hover:underline" onClick={() => setReplyTo(null)}>cancel</button></p>}
        <textarea required rows={2} className={textarea} placeholder="Write a comment or ask a question…" value={body} onChange={(e) => setBody(e.target.value)} />
        <div className="flex flex-wrap items-end gap-3">
          {!replyTo && <Field label="Type"><Select value={kind} onChange={(e) => setKind(e.target.value)}><option value="comment">Comment</option><option value="question">Question</option><option value="clarification">Clarification needed</option></Select></Field>}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-500">Notify:</span>
            {people.data?.map((p) => (
              <label key={p.user_id} className="flex items-center gap-1 rounded-full border border-slate-200 px-2 py-0.5" title={p.why}>
                <input type="checkbox" checked={mentions.includes(p.user_id)} onChange={(e) => setMentions(e.target.checked ? [...mentions, p.user_id] : mentions.filter((m) => m !== p.user_id))} />{p.full_name}
              </label>
            ))}
          </div>
        </div>
        <ErrorNote error={send.error} />
        <div><Button type="submit" disabled={send.isPending || !body.trim()}>{replyTo ? "Send reply" : kind === "question" ? "Ask question" : "Post"}</Button></div>
      </form>
    </Card>
  );
}
