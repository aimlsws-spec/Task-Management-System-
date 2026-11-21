import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { fmtDateTime, fmtDay, OverdueBadge, PriorityChip, StatusBadge, type Workload } from "@/components/task-ui";
import { STATUS_TONE, useEmployees, type Person, type ProjectSummary } from "@/pages/Projects";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Point = {
  id: number; title: string; details: string | null; expected_result: string | null; status: "open" | "assigned" | "done" | "cancelled";
  is_done: boolean;
  task: null | { id: number; task_no: string; status: string; assignee: Person | null; due_at: string; review_stage: string | null };
};
type TaskRow = { id: number; task_no: string; title: string; status: string; priority: string; assignee: Person; due_at: string; is_overdue: boolean; review_stage: string | null };
type Detail = ProjectSummary & {
  assignee: Person | null; progress_pct: number;
  members: Person[]; points: Point[]; tasks: TaskRow[]; completed_at: string | null; review_note: string | null; reviewed_by: string | null;
  can_manage: boolean; can_complete: boolean;
};

const POINT_TONE = { open: "orange", assigned: "blue", done: "green", cancelled: "grey" } as const;
const POINT_LABEL = { open: "To do", assigned: "In progress", done: "Done", cancelled: "Task cancelled" } as const;
const area = "block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-card focus:border-indigo-500 focus:outline-none focus:ring-4 focus:ring-indigo-100";

function stageLabel(stage: string | null) {
  return stage === "qa" ? "Waiting for QA testing" : stage === "head" ? "Waiting for the head" : stage === "leadership" ? "Waiting for CEO / Owner" : null;
}

export function ProjectDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const { me } = useAuth();
  const q = useQuery({ queryKey: ["project", id], queryFn: () => api<Detail>(`/projects/${id}`), refetchInterval: 5000 });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["project", id] }); qc.invalidateQueries({ queryKey: ["projects"] }); qc.invalidateQueries({ queryKey: ["tasks"] }); };
  const [note, setNote] = useState("");
  const complete = useMutation({ mutationFn: () => api(`/projects/${id}/complete`, { body: { note: note || null } }), onSuccess: refresh });
  const setStatus = useMutation({ mutationFn: (status: string) => api(`/projects/${id}`, { method: "PATCH", body: { status } }), onSuccess: refresh });
  const tz = me?.user.timezone;
  const d = q.data;
  if (q.isLoading) return <Spinner />;
  if (!d) return <ErrorNote error={q.error} />;
  const donePoints = d.points.filter((p) => p.is_done || p.status === "done").length;
  const pct = d.counts.tasks
    ? Math.round((d.counts.done_tasks / d.counts.tasks) * 100)
    : d.points.length
    ? Math.round((donePoints / d.points.length) * 100)
    : d.progress_pct || 0;
  return (
    <>
      <PageHeader
        title={d.name}
        subtitle={`${d.code} · ${d.counts.done_tasks}/${d.counts.tasks} tasks done · ${donePoints}/${d.points.length} points completed`}
        actions={d.can_manage && d.status !== "completed" ? (
          <Select className="w-40" value={d.status} onChange={(e) => setStatus.mutate(e.target.value)} aria-label="Project status">
            <option value="active">Active</option><option value="on_hold">On hold</option><option value="archived">Archived</option>
          </Select>
        ) : undefined}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge tone={STATUS_TONE[d.status] ?? "grey"}>{d.status.replace("_", " ")}</Badge>
        {d.ready_for_review && <Badge tone="purple">Ready for review</Badge>}
        {d.counts.awaiting_review > 0 && <Badge tone="purple">{d.counts.awaiting_review} task{d.counts.awaiting_review === 1 ? "" : "s"} awaiting review</Badge>}
        <div className="ml-auto h-1.5 w-40 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} /></div>
      </div>

      {d.ready_for_review && d.can_complete && (
        <Card className="mb-5 border-violet-200 bg-violet-50 p-5">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 text-violet-600" size={20} />
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-violet-900">Everything is done and reviewed</h2>
              <p className="text-sm text-violet-800">Check the expected result below. When you are satisfied, mark the project completed. Adding a new point later reopens it.</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Input className="max-w-sm bg-white" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                <Button disabled={complete.isPending} onClick={() => complete.mutate()}>Mark project completed</Button>
              </div>
              <div className="mt-2"><ErrorNote error={complete.error} /></div>
            </div>
          </div>
        </Card>
      )}
      {d.status === "completed" && (
        <Card className="mb-5 border-green-200 bg-green-50 p-4 text-sm text-green-900">
          <b>Completed</b> {d.completed_at && fmtDateTime(d.completed_at, tz)}{d.reviewed_by && <> · reviewed by {d.reviewed_by}</>}{d.review_note && <> · “{d.review_note}”</>}
        </Card>
      )}

      <div className="mb-5 grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold text-brand-ink">Expected result</h2>
          <p className="whitespace-pre-wrap text-sm text-slate-700">{d.expected_result || <span className="text-slate-400">Not written yet.</span>}</p>
          {d.description && <><h2 className="mb-1 mt-4 text-sm font-semibold text-brand-ink">About</h2><p className="whitespace-pre-wrap text-sm text-slate-600">{d.description}</p></>}
        </Card>
        <TeamCard d={d} onSaved={refresh} />
      </div>

      <Points d={d} onChanged={refresh} />

      <Card className="mt-5 overflow-x-auto">
        <div className="p-4 pb-0"><h2 className="text-sm font-semibold text-brand-ink">Tasks in this project</h2></div>
        {d.tasks.length === 0 ? <EmptyState title="No tasks yet" hint="Assign a point above to create the first task." /> : (
          <table className="mt-2 w-full text-left text-sm">
            <thead><tr><th className="p-3">Task</th><th className="p-3">Assignee</th><th className="p-3">Status</th><th className="p-3">Deadline</th></tr></thead>
            <tbody>
              {d.tasks.map((t) => (
                <tr key={t.id}>
                  <td className="p-3"><Link to={`/tasks/${t.id}`} className="font-medium text-brand-ink hover:text-indigo-700 hover:underline">{t.title}</Link><div className="text-xs text-slate-500">{t.task_no}</div></td>
                  <td className="p-3">{t.assignee.full_name}</td>
                  <td className="p-3"><div className="flex flex-wrap items-center gap-1"><StatusBadge status={t.status} /><PriorityChip priority={t.priority} />{t.is_overdue && <OverdueBadge />}{stageLabel(t.review_stage) && <Badge tone="purple">{stageLabel(t.review_stage)}</Badge>}</div></td>
                  <td className="whitespace-nowrap p-3">{fmtDay(t.due_at, tz)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

function TeamCard({ d, onSaved }: { d: Detail; onSaved: () => void }) {
  const emps = useEmployees();
  const [editing, setEditing] = useState(false);
  const [assignee, setAssignee] = useState(d.assignee ? String(d.assignee.id) : "");
  const [head, setHead] = useState(d.head ? String(d.head.id) : "");
  const [qa, setQa] = useState(d.qa ? String(d.qa.id) : "");
  const [dates, setDates] = useState({ starts_on: d.starts_on ?? "", ends_on: d.ends_on ?? "" });
  const [team, setTeam] = useState<number[]>(d.members.map((m) => m.id));
  const save = useMutation({
    mutationFn: () => api(`/projects/${d.id}`, { method: "PATCH", body: { assignee_id: assignee ? Number(assignee) : null, head_employee_id: head ? Number(head) : null, qa_employee_id: qa ? Number(qa) : null, member_ids: team, starts_on: dates.starts_on || null, ...(dates.ends_on ? { ends_on: dates.ends_on } : {}) } }),
    onSuccess: () => { setEditing(false); onSaved(); },
  });
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold text-brand-ink">Project team & leaders</h2>{d.can_manage && !editing && <Button variant="ghost" className="py-1" onClick={() => setEditing(true)}>Edit</Button>}</div>
      {!editing ? (
        <div className="space-y-3 text-sm">
          <div><div className="text-xs text-slate-500">Assigned employee</div>{d.assignee ? <div className="font-medium text-brand-ink">{d.assignee.full_name}</div> : <div className="text-slate-500">No primary employee assigned</div>}</div>
          <div><div className="text-xs text-slate-500">Project head</div>{d.head ? <div className="font-medium">{d.head.full_name}</div> : <div className="text-slate-500">None: tasks are assigned directly and go straight to the CEO/Owner for review.</div>}</div>
          <div><div className="text-xs text-slate-500">QA tester</div>{d.qa ? <div className="font-medium">{d.qa.full_name}</div> : <div className="text-slate-500">None: finished work goes straight to the head or the CEO/Owner.</div>}</div>
          <div><div className="text-xs text-slate-500">Deadline</div><div>{d.ends_on ? <span className="font-medium">{d.ends_on}{d.starts_on ? ` (started ${d.starts_on})` : ""}</span> : <span className="text-slate-500">Not set: edit and add one</span>}</div></div>
          <div><div className="text-xs text-slate-500">Team</div>{d.members.length ? <ul className="mt-1 space-y-0.5">{d.members.map((m) => <li key={m.id}>{m.full_name}</li>)}</ul> : <div className="text-slate-500">Open: tasks can go to anyone you can assign to.</div>}</div>
        </div>
      ) : (
        <div className="space-y-3">
          <Field label="Assigned employee (optional)">
            <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}><option value="">No primary assignee</option>{emps.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}</Select>
          </Field>
          <Field label="Project head">
            <Select value={head} onChange={(e) => setHead(e.target.value)}><option value="">Fallback to department head</option>{emps.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}</Select>
          </Field>
          <Field label="QA tester">
            <Select value={qa} onChange={(e) => setQa(e.target.value)}><option value="">No QA</option>{emps.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}</Select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Start date"><Input type="date" value={dates.starts_on} onChange={(e) => setDates({ ...dates, starts_on: e.target.value })} /></Field>
            <Field label="Project deadline (required)"><Input required type="date" min={dates.starts_on || undefined} value={dates.ends_on} onChange={(e) => setDates({ ...dates, ends_on: e.target.value })} /></Field>
          </div>
          <div className="max-h-44 overflow-y-auto rounded-lg border border-hairline">
            {emps.data?.map((e) => (
              <label key={e.id} className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-slate-50">
                <input type="checkbox" checked={team.includes(e.id)} onChange={() => setTeam((t) => (t.includes(e.id) ? t.filter((x) => x !== e.id) : [...t, e.id]))} /> {e.full_name}
              </label>
            ))}
          </div>
          <div className="flex gap-2"><Button disabled={save.isPending} onClick={() => save.mutate()}>Save</Button><Button variant="outline" onClick={() => setEditing(false)}>Cancel</Button></div>
          <ErrorNote error={save.error} />
        </div>
      )}
    </Card>
  );
}

function Points({ d, onChanged }: { d: Detail; onChanged: () => void }) {
  const { me } = useAuth();
  const [adding, setAdding] = useState(false);
  const [assigning, setAssigning] = useState<number | null>(null);
  const [f, setF] = useState({ title: "", details: "", expected_result: "" });
  const add = useMutation({
    mutationFn: () => api(`/projects/${d.id}/points`, { body: { title: f.title, details: f.details || null, expected_result: f.expected_result || null } }),
    onSuccess: () => { setF({ title: "", details: "", expected_result: "" }); setAdding(false); onChanged(); },
  });
  const toggle = useMutation({
    mutationFn: (pid: number) => api(`/projects/${d.id}/points/${pid}/toggle`, { method: "PATCH" }),
    onSuccess: onChanged,
  });
  const remove = useMutation({ mutationFn: (pid: number) => api(`/projects/${d.id}/points/${pid}`, { method: "DELETE" }), onSuccess: onChanged });
  const submit = (e: FormEvent) => { e.preventDefault(); add.mutate(); };
  const editable = d.can_manage && d.status !== "archived";
  const canToggle = editable || d.members.some((m) => m.id === me?.employee?.id) || d.assignee?.id === me?.employee?.id || d.head?.id === me?.employee?.id;
  return (
    <Card>
      <div className="flex items-center justify-between p-4 pb-2">
        <h2 className="text-sm font-semibold text-brand-ink">Project points (checklist / scope)</h2>
        {editable && <Button variant="outline" className="py-1.5" onClick={() => setAdding((v) => !v)}><Plus size={15} /> {adding ? "Close" : "Add a point"}</Button>}
      </div>
      {adding && (
        <form onSubmit={submit} className="mx-4 mb-3 grid gap-3 rounded-lg bg-slate-50 p-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><Field label="What needs to be done?"><Input required minLength={2} autoFocus value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field></div>
          <Field label="Details (optional)"><textarea rows={2} value={f.details} onChange={(e) => setF({ ...f, details: e.target.value })} className={area} /></Field>
          <Field label="Expected result (optional)"><textarea rows={2} value={f.expected_result} onChange={(e) => setF({ ...f, expected_result: e.target.value })} className={area} /></Field>
          <div className="flex items-center gap-3 sm:col-span-2"><Button type="submit" disabled={add.isPending}>Add point</Button><ErrorNote error={add.error} /></div>
        </form>
      )}
      {d.points.length === 0 ? <EmptyState title="No points yet" hint="Add what you remember now; you can add more at any time." /> : (
        <ul className="divide-y divide-hairline">
          {d.points.map((x) => (
            <li key={x.id} className="p-4">
              <div className="flex flex-wrap items-start gap-3">
                <div className="mt-0.5 flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={x.is_done || x.status === "done"}
                    onChange={() => toggle.mutate(x.id)}
                    disabled={!canToggle}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                    title={x.is_done ? "Mark not done" : "Mark done"}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className={`font-medium ${x.is_done || x.status === "done" ? "line-through text-slate-400" : "text-slate-900"}`}>{x.title}</div>
                  {x.details && <p className="mt-0.5 whitespace-pre-wrap text-sm text-slate-600">{x.details}</p>}
                  {x.expected_result && <p className="mt-0.5 text-sm text-slate-500"><span className="font-medium text-slate-600">Expected: </span>{x.expected_result}</p>}
                  {x.task && (
                    <p className="mt-1 text-xs text-slate-500">
                      <Link to={`/tasks/${x.task.id}`} className="font-medium text-indigo-600 hover:underline">{x.task.task_no}</Link> · {x.task.assignee?.full_name} · <StatusBadge status={x.task.status} />
                      {stageLabel(x.task.review_stage) && <> · {stageLabel(x.task.review_stage)}</>}
                    </p>
                  )}
                </div>
                <Badge tone={POINT_TONE[x.status]}>{POINT_LABEL[x.status]}</Badge>
                {editable && (x.status === "open" || x.status === "cancelled") && (
                  <div className="flex gap-1">
                    <Button variant="outline" className="py-1" onClick={() => setAssigning(assigning === x.id ? null : x.id)}>{assigning === x.id ? "Close" : "Assign as task"}</Button>
                    <Button variant="ghost" className="py-1 text-red-600" aria-label={`Remove ${x.title}`} onClick={() => confirm(`Remove “${x.title}”?`) && remove.mutate(x.id)}>Remove</Button>
                  </div>
                )}
              </div>
              {assigning === x.id && <AssignForm d={d} pointId={x.id} onDone={() => { setAssigning(null); onChanged(); }} />}
            </li>
          ))}
        </ul>
      )}
      <div className="px-4 pb-4"><ErrorNote error={remove.error} /></div>
    </Card>
  );
}

function AssignForm({ d, pointId, onDone }: { d: Detail; pointId: number; onDone: () => void }) {
  const people = useQuery({ queryKey: ["workload"], queryFn: () => api<Workload[]>("/workload") });
  const [f, setF] = useState({ assignee: "", priority: "medium", due: "" });
  const allowed = new Set([...d.members.map((m) => m.id), ...(d.head ? [d.head.id] : [])]);
  const options = (people.data ?? []).filter((p) => !p.is_me && (allowed.size === 0 || allowed.has(p.employee_id)));
  const assign = useMutation({
    mutationFn: () => api(`/projects/${d.id}/points/${pointId}/assign`, { body: { assignee_id: Number(f.assignee), priority: f.priority, due_date: f.due } }),
    onSuccess: onDone,
  });
  const submit = (e: FormEvent) => { e.preventDefault(); assign.mutate(); };
  return (
    <form onSubmit={submit} className="mt-3 grid gap-3 rounded-lg bg-slate-50 p-4 sm:grid-cols-3">
      <Field label={allowed.size ? "Assign to (project team)" : "Assign to"}>
        <Select required value={f.assignee} onChange={(e) => setF({ ...f, assignee: e.target.value })}>
          <option value="">Choose…</option>
          {options.map((p) => <option key={p.employee_id} value={p.employee_id}>{p.full_name}</option>)}
        </Select>
      </Field>
      <Field label="Priority"><Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{["critical", "high", "medium", "low"].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}</Select></Field>
      <Field label="Deadline"><Input required type="date" value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} /></Field>
      <div className="flex items-center gap-3 sm:col-span-3"><Button type="submit" disabled={assign.isPending}>Assign task</Button><ErrorNote error={assign.error} />{!people.isLoading && options.length === 0 && <span className="text-sm text-slate-500">No one available to assign.</span>}</div>
    </form>
  );
}
