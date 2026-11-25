import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Plus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { fmtDateTime, fmtDay, OverdueBadge, PriorityChip, PRIORITY_OPTIONS, StatusBadge, type Workload } from "@/components/task-ui";
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
  can_manage: boolean; can_head_complete?: boolean; can_complete: boolean;
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
  const nav = useNavigate();
  const { me } = useAuth();
  const isLeadership = Boolean(me?.roles.includes("owner") || me?.roles.includes("ceo"));
  const q = useQuery({ queryKey: ["project", id], queryFn: () => api<Detail>(`/projects/${id}`), refetchInterval: 5000 });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["project", id] }); qc.invalidateQueries({ queryKey: ["projects"] }); qc.invalidateQueries({ queryKey: ["tasks"] }); };
  const [note, setNote] = useState("");
  const complete = useMutation({ mutationFn: () => api(`/projects/${id}/complete`, { body: { note: note || null } }), onSuccess: refresh });
  const setStatus = useMutation({ mutationFn: (status: string) => api(`/projects/${id}`, { method: "PATCH", body: { status } }), onSuccess: refresh });
  const deleteProject = useMutation({
    mutationFn: () => api(`/projects/${id}`, { method: "DELETE" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["projects"] }); nav("/projects"); },
  });
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
        subtitle={`${d.code} · ${d.counts.done_tasks}/${d.counts.tasks} tasks done · ${donePoints}/${d.points.length} points completed${d.created_by ? ` · Created by ${d.created_by.full_name}` : ""}`}
        actions={
          <div className="flex items-center gap-2">
            {isLeadership && d.can_manage && d.status !== "completed" && (
              <Select className="w-40" value={d.status} onChange={(e) => setStatus.mutate(e.target.value)} aria-label="Project status">
                <option value="active">Active</option><option value="on_hold">On hold</option><option value="archived">Archived</option>
              </Select>
            )}
            {isLeadership && (
              <Button
                variant="outline"
                className="text-red-600 hover:bg-red-50 hover:border-red-300"
                onClick={() => {
                  if (confirm(`Are you sure you want to delete project "${d.name}" and all its points/tasks?`)) {
                    deleteProject.mutate();
                  }
                }}
                disabled={deleteProject.isPending}
              >
                Delete project
              </Button>
            )}
          </div>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {d.company && (
          <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 border border-indigo-200">
            {d.company.name} ({d.company.code})
          </span>
        )}
        <PriorityChip priority={d.priority || "medium"} />
        <Badge tone={STATUS_TONE[d.status] ?? "grey"}>{d.status.replace("_", " ")}</Badge>
        {d.ready_for_review && <Badge tone="purple">Ready for review</Badge>}
        {d.counts.awaiting_review > 0 && <Badge tone="purple">{d.counts.awaiting_review} task{d.counts.awaiting_review === 1 ? "" : "s"} awaiting review</Badge>}
        <div className="ml-auto h-1.5 w-40 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} /></div>
      </div>

      {d.ready_for_review && d.can_head_complete && (
        <Card className="mb-5 border-blue-200 bg-blue-50 p-5">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 text-blue-600" size={20} />
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-blue-900">All points & tasks finished — Head Review</h2>
              <p className="text-sm text-blue-800">Check the deliverables against the expected result. When verified, submit this project to the Owner and CEO for final sign-off.</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Input className="max-w-sm bg-white" placeholder="Review note for Owner / CEO (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                <Button disabled={complete.isPending} onClick={() => complete.mutate()}>Review & Submit to Owner/CEO Panel</Button>
              </div>
              <div className="mt-2"><ErrorNote error={complete.error} /></div>
            </div>
          </div>
        </Card>
      )}

      {d.head_reviewed_at && d.status !== "completed" && (
        <Card className="mb-5 border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-950">
          <b>Head Review Submitted:</b> Reviewed by {d.head_reviewed_by ?? "Head"} on {fmtDateTime(d.head_reviewed_at, tz)}
          {d.head_review_note && <div className="mt-1 text-slate-700">“{d.head_review_note}”</div>}
        </Card>
      )}

      {d.ready_for_review && d.can_complete && (
        <Card className="mb-5 border-violet-200 bg-violet-50 p-5">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 text-violet-600" size={20} />
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-violet-900">Final Leadership Review (Owner / CEO)</h2>
              <p className="text-sm text-violet-800">Check the expected result below and head review notes. When satisfied, mark the project completed. Adding a new point later reopens it.</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Input className="max-w-sm bg-white" placeholder="Completion note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
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
          {d.head_reviewed_by && <div className="mt-1 text-xs text-green-800">Head sign-off: {d.head_reviewed_by}{d.head_review_note ? ` — “${d.head_review_note}”` : ""}</div>}
        </Card>
      )}

      <div className="mb-5 grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <h2 className="mb-2 text-sm font-semibold text-brand-ink">Expected result</h2>
          <p className="whitespace-pre-wrap text-sm text-slate-700">{d.expected_result || <span className="text-slate-400">Not written yet.</span>}</p>
          {d.special_note && <><h2 className="mb-1 mt-4 text-sm font-semibold text-brand-ink">Special Note</h2><p className="whitespace-pre-wrap text-sm text-slate-600">{d.special_note}</p></>}
          {d.description && <><h2 className="mb-1 mt-4 text-sm font-semibold text-brand-ink">About</h2><p className="whitespace-pre-wrap text-sm text-slate-600">{d.description}</p></>}
        </Card>
        <TeamCard d={d} onSaved={refresh} />
      </div>

      <Points d={d} onChanged={refresh} />

      <Card className="mt-5 overflow-x-auto">
        <div className="p-4 pb-0 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-brand-ink">Tasks in this project ({d.tasks.length})</h2>
          {d.can_manage && d.status !== "archived" && (
            <Link to={`/tasks/new?project_id=${d.id}`}>
              <Button variant="outline" className="py-1 text-xs">
                <Plus size={14} className="mr-1 inline" /> Add task to project
              </Button>
            </Link>
          )}
        </div>
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
  const { me } = useAuth();
  const isLeadership = Boolean(me?.roles.includes("owner") || me?.roles.includes("ceo"));
  const emps = useEmployees();
  const [editing, setEditing] = useState(false);
  const [assignee, setAssignee] = useState(d.assignee ? String(d.assignee.id) : "");
  const [selectedHeads, setSelectedHeads] = useState<number[]>(() => {
    if (d.heads && d.heads.length) return d.heads.map((h) => h.id);
    const initial: number[] = [];
    if (d.head) initial.push(d.head.id);
    if (d.sub_head) initial.push(d.sub_head.id);
    return initial;
  });
  const [selectedQAs, setSelectedQAs] = useState<number[]>(d.qa_members ? d.qa_members.map((q) => q.id) : (d.qa ? [d.qa.id] : []));
  const [dates, setDates] = useState({ starts_on: d.starts_on ?? "", ends_on: d.ends_on ?? "" });
  const [team, setTeam] = useState<number[]>(d.members.map((m) => m.id));
  const [headSearch, setHeadSearch] = useState("");
  const [qaSearch, setQaSearch] = useState("");
  const [teamSearch, setTeamSearch] = useState("");

  const filteredHeads = useMemo(() => {
    const q = headSearch.trim().toLowerCase();
    if (!q) return emps.data ?? [];
    return (emps.data ?? []).filter((e) => e.full_name.toLowerCase().includes(q) || (e.job_title && e.job_title.toLowerCase().includes(q)));
  }, [emps.data, headSearch]);

  const filteredQAs = useMemo(() => {
    const q = qaSearch.trim().toLowerCase();
    if (!q) return emps.data ?? [];
    return (emps.data ?? []).filter((e) => e.full_name.toLowerCase().includes(q) || (e.job_title && e.job_title.toLowerCase().includes(q)));
  }, [emps.data, qaSearch]);

  const filteredTeam = useMemo(() => {
    const q = teamSearch.trim().toLowerCase();
    if (!q) return emps.data ?? [];
    return (emps.data ?? []).filter((e) => e.full_name.toLowerCase().includes(q) || (e.job_title && e.job_title.toLowerCase().includes(q)));
  }, [emps.data, teamSearch]);

  const save = useMutation({
    mutationFn: () => api(`/projects/${d.id}`, {
      method: "PATCH",
      body: {
        assignee_id: assignee ? Number(assignee) : null,
        head_employee_id: selectedHeads[0] ?? null,
        sub_head_employee_id: selectedHeads[1] ?? null,
        head_employee_ids: selectedHeads,
        qa_employee_id: selectedQAs[0] ?? null,
        qa_employee_ids: selectedQAs,
        member_ids: team,
        starts_on: dates.starts_on || null,
        ...(dates.ends_on ? { ends_on: dates.ends_on } : {}),
      },
    }),
    onSuccess: () => { setEditing(false); onSaved(); },
  });
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-brand-ink">Project team & leaders</h2>
        {isLeadership && d.can_manage && !editing && (
          <Button variant="ghost" className="py-1" onClick={() => setEditing(true)}>Edit</Button>
        )}
      </div>
      {!editing ? (
        <div className="space-y-3 text-sm">
          {d.created_by && (
            <div>
              <div className="text-xs text-slate-500">Created by</div>
              <div className="font-medium text-brand-ink">{d.created_by.full_name}</div>
            </div>
          )}
          <div>
            <div className="text-xs text-slate-500">Assigned employee</div>
            {d.assignee ? <div className="font-medium text-brand-ink">{d.assignee.full_name}</div> : <div className="text-slate-500">No primary employee assigned</div>}
          </div>
          <div>
            <div className="text-xs text-slate-500">Project heads & sub-heads</div>
            {d.heads && d.heads.length > 0 ? (
              <div className="font-medium text-brand-ink">{d.heads.map((h) => h.full_name).join(", ")}</div>
            ) : d.head ? (
              <div className="font-medium text-brand-ink">
                {d.head.full_name}{d.sub_head ? `, ${d.sub_head.full_name} (Sub-Head)` : ""}
              </div>
            ) : (
              <div className="text-slate-500">None: fallback to department head & sub-head</div>
            )}
          </div>
          <div>
            <div className="text-xs text-slate-500">Assigned QA members</div>
            {d.qa_members && d.qa_members.length ? (
              <div className="font-medium">{d.qa_members.map((q) => q.full_name).join(", ")}</div>
            ) : d.qa ? (
              <div className="font-medium">{d.qa.full_name}</div>
            ) : (
              <div className="text-slate-500">None: finished work goes straight to the head or CEO/Owner.</div>
            )}
          </div>
          <div>
            <div className="text-xs text-slate-500">Deadline</div>
            <div>{d.ends_on ? <span className="font-medium">{d.ends_on}{d.starts_on ? ` (started ${d.starts_on})` : ""}</span> : <span className="text-slate-500">Not set: edit and add one</span>}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Team</div>
            {d.members.length ? (
              <ul className="mt-1 space-y-0.5">{d.members.map((m) => <li key={m.id}>{m.full_name}</li>)}</ul>
            ) : (
              <div className="text-slate-500">Open: tasks can go to anyone you can assign to.</div>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <Field label="Assigned employee (optional)">
            <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">No primary assignee</option>
              {emps.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </Select>
          </Field>
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-medium text-slate-700">
              <span>Project Heads / Sub-Heads ({selectedHeads.length} selected)</span>
              <span className="text-slate-400">Can select multiple</span>
            </div>
            <input
              type="text"
              placeholder="Search heads..."
              value={headSearch}
              onChange={(e) => setHeadSearch(e.target.value)}
              className="mb-1 w-full rounded border border-hairline px-2 py-1 text-xs"
            />
            <div className="max-h-32 overflow-y-auto rounded-lg border border-hairline p-1">
              {filteredHeads.map((e) => (
                <label key={e.id} className="flex cursor-pointer items-center gap-2 px-2 py-1 text-xs hover:bg-slate-50">
                  <input
                    type="checkbox"
                    checked={selectedHeads.includes(e.id)}
                    onChange={() => setSelectedHeads((curr) => curr.includes(e.id) ? curr.filter((x) => x !== e.id) : [...curr, e.id])}
                  />
                  <span>{e.full_name} {e.job_title ? `(${e.job_title})` : ""}</span>
                </label>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-slate-500">If none selected, assigned employee's department Head & Sub-Head will be in loop automatically.</p>
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-medium text-slate-700">
              <span>Assigned QA members ({selectedQAs.length} selected)</span>
              <span className="text-slate-400">Can select multiple</span>
            </div>
            <input
              type="text"
              placeholder="Search QA members..."
              value={qaSearch}
              onChange={(e) => setQaSearch(e.target.value)}
              className="mb-1 w-full rounded border border-hairline px-2 py-1 text-xs"
            />
            <div className="max-h-32 overflow-y-auto rounded-lg border border-hairline p-1">
              {filteredQAs.map((e) => (
                <label key={e.id} className="flex cursor-pointer items-center gap-2 px-2 py-1 text-xs hover:bg-slate-50">
                  <input
                    type="checkbox"
                    checked={selectedQAs.includes(e.id)}
                    onChange={() => setSelectedQAs((qas) => (qas.includes(e.id) ? qas.filter((x) => x !== e.id) : [...qas, e.id]))}
                  />
                  <span>{e.full_name} {e.job_title ? `(${e.job_title})` : ""}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Start date"><Input type="date" value={dates.starts_on} onChange={(e) => setDates({ ...dates, starts_on: e.target.value })} /></Field>
            <Field label="Project deadline (required)"><Input required type="date" min={dates.starts_on || undefined} value={dates.ends_on} onChange={(e) => setDates({ ...dates, ends_on: e.target.value })} /></Field>
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-medium text-slate-700">
              <span>Team members ({team.length} selected)</span>
            </div>
            <input
              type="text"
              placeholder="Search team members..."
              value={teamSearch}
              onChange={(e) => setTeamSearch(e.target.value)}
              className="mb-1 w-full rounded border border-hairline px-2 py-1 text-xs"
            />
            <div className="max-h-44 overflow-y-auto rounded-lg border border-hairline p-1">
              {filteredTeam.map((e) => (
                <label key={e.id} className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-xs hover:bg-slate-50">
                  <input type="checkbox" checked={team.includes(e.id)} onChange={() => setTeam((t) => (t.includes(e.id) ? t.filter((x) => x !== e.id) : [...t, e.id]))} /> {e.full_name} {e.job_title ? `(${e.job_title})` : ""}
                </label>
              ))}
            </div>
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
  const isLeadership = Boolean(me?.roles.includes("owner") || me?.roles.includes("ceo"));
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
  const canAddPoint = d.can_manage && d.status !== "archived";
  const editable = isLeadership && d.can_manage && d.status !== "archived";
  const isHead = (d.heads && d.heads.some((h) => h.id === me?.employee?.id)) || d.head?.id === me?.employee?.id || d.sub_head?.id === me?.employee?.id;
  const canToggle = editable || d.members.some((m) => m.id === me?.employee?.id) || d.assignee?.id === me?.employee?.id || isHead;
  return (
    <Card>
      <div className="flex items-center justify-between p-4 pb-2">
        <h2 className="text-sm font-semibold text-brand-ink">Project points (checklist / scope)</h2>
        {canAddPoint && <Button variant="outline" className="py-1.5" onClick={() => setAdding((v) => !v)}><Plus size={15} /> {adding ? "Close" : "Add a point"}</Button>}
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
                {(x.status === "open" || x.status === "cancelled") && (
                  <div className="flex gap-1">
                    {d.can_manage && <Button variant="outline" className="py-1" onClick={() => setAssigning(assigning === x.id ? null : x.id)}>{assigning === x.id ? "Close" : "Assign as task"}</Button>}
                    {isLeadership && <Button variant="ghost" className="py-1 text-red-600" aria-label={`Remove ${x.title}`} onClick={() => confirm(`Remove “${x.title}”?`) && remove.mutate(x.id)}>Remove</Button>}
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
  const [f, setF] = useState({ assignee: "", priority: "medium", due: "", special_note: "" });
  const headIds = (d.heads ?? []).map((h) => h.id);
  if (d.head) headIds.push(d.head.id);
  if (d.sub_head) headIds.push(d.sub_head.id);
  const allowed = new Set([...d.members.map((m) => m.id), ...headIds]);
  const options = (people.data ?? []).filter((p) => !p.is_me && (allowed.size === 0 || allowed.has(p.employee_id)));
  const assign = useMutation({
    mutationFn: () => api(`/projects/${d.id}/points/${pointId}/assign`, {
      body: {
        assignee_id: Number(f.assignee),
        priority: f.priority,
        due_date: f.due || null,
        special_note: f.special_note || null,
      },
    }),
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
      <Field label="Priority"><Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{PRIORITY_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</Select></Field>
      <Field label="Deadline (optional)"><Input type="date" value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} placeholder="Inherits project deadline" /></Field>
      <div className="sm:col-span-3">
        <Field label="Special Note (optional)"><Input value={f.special_note} onChange={(e) => setF({ ...f, special_note: e.target.value })} placeholder="Special note or instructions..." /></Field>
      </div>
      <div className="flex items-center gap-3 sm:col-span-3"><Button type="submit" disabled={assign.isPending}>Assign task</Button><ErrorNote error={assign.error} />{!people.isLoading && options.length === 0 && <span className="text-sm text-slate-500">No one available to assign.</span>}</div>
    </form>
  );
}
