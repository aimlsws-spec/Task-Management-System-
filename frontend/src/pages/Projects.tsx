import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, Plus, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { PriorityChip, PRIORITY_OPTIONS } from "@/components/task-ui";
import { AiAssistModal } from "@/components/AiAssistModal";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export type Person = { id: number; full_name: string; job_title: string | null };
export type ProjectSummary = {
  id: number; code: string; name: string; description: string | null; status: string; expected_result: string | null;
  priority?: string; special_note?: string | null;
  company_id?: number;
  company?: { id: number; name: string; code: string } | null;
  head: Person | null; sub_head?: Person | null; heads?: Person[]; qa: Person | null; qa_members?: Person[];
  created_by?: Person | null;
  head_reviewed_at?: string | null; head_reviewed_by?: string | null; head_review_note?: string | null;
  can_head_complete?: boolean; can_complete?: boolean;
  starts_on: string | null; ends_on: string | null; ready_for_review: boolean;
  assignee?: Person | null; progress_pct?: number;
  counts: { points: number; open_points: number; tasks: number; done_tasks: number; awaiting_review: number };
};
type Emp = Person & { is_active: boolean; company_id?: number; company_ids?: number[]; is_shared?: boolean };

export const STATUS_TONE: Record<string, "green" | "grey" | "orange" | "indigo"> = { active: "green", on_hold: "orange", completed: "indigo", archived: "grey" };

export function useEmployees(companyId?: number | string | null) {
  return useQuery({
    queryKey: ["employees", "pick", companyId ?? "all"],
    queryFn: () => api<{ items: Emp[] }>("/employees", { params: { page_size: 200 } }),
    select: (r) => r.items.filter((e) => {
      if (!e.is_active) return false;
      if (!companyId) return true;
      const cid = Number(companyId);
      if (e.is_shared) return true;
      if (e.company_id === cid) return true;
      if (e.company_ids && e.company_ids.includes(cid)) return true;
      return false;
    }),
  });
}

/** Projects: what the Owner/CEO wants (expected result), who heads it, the team, and the points to be assigned over time. */
export function Projects() {
  const { can } = useAuth();
  const [sp, setSp] = useSearchParams();
  const companyFilter = sp.get("company_id") || "";
  const setCompanyFilter = (cid: string) => {
    const next = new URLSearchParams(sp);
    if (cid) next.set("company_id", cid); else next.delete("company_id");
    setSp(next, { replace: true });
  };
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<{ id: number; name: string; code: string }[]>("/companies") });
  const list = useQuery({
    queryKey: ["projects", companyFilter],
    queryFn: () => api<ProjectSummary[]>("/projects", { params: { company_id: companyFilter || undefined } }),
    refetchInterval: 6000,
  });
  const [creating, setCreating] = useState(sp.get("new") === "1");
  return (
    <>
      <PageHeader
        title="Projects"
        subtitle="Write down what you want and what result you expect. Add more points whenever you remember them, then assign each to an employee."
        actions={can("project.manage") ? <Button onClick={() => setCreating((v) => !v)}><Plus size={16} /> {creating ? "Close" : "New project"}</Button> : undefined}
      />
      {companies.data && companies.data.length > 1 && (
        <div className="mb-4 flex items-center gap-2">
          <span className="text-xs font-medium text-slate-600">Company:</span>
          <Select className="w-56 text-sm" value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
            <option value="">All companies</option>
            {companies.data.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
          </Select>
        </div>
      )}
      {creating && <CreateProject onDone={() => setCreating(false)} initialCompanyId={companyFilter ? Number(companyFilter) : undefined} />}
      {list.isLoading ? <Spinner /> : !list.data?.length ? (
        <Card><EmptyState icon={<FolderKanban size={18} />} title="No projects yet" hint={can("project.manage") ? "Create your first project with “New project”." : "You are not part of any project yet."} /></Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {list.data.map((p) => {
            const pct = p.counts.tasks ? Math.round((p.counts.done_tasks / p.counts.tasks) * 100) : 0;
            return (
              <Link key={p.id} to={`/projects/${p.id}`} className="group block rounded-xl border border-hairline bg-white p-5 shadow-card transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-pop">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-base font-semibold text-brand-ink group-hover:text-indigo-700">{p.name}</span>
                      {p.company && (
                        <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-700 border border-indigo-200">
                          {p.company.code || p.company.name}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">{p.code}</div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1.5">
                    <PriorityChip priority={p.priority || "medium"} />
                    {p.ready_for_review && <Badge tone="purple">Ready for review</Badge>}
                    <Badge tone={STATUS_TONE[p.status] ?? "grey"}>{p.status.replace("_", " ")}</Badge>
                  </div>
                </div>
                {p.expected_result && <p className="mt-3 line-clamp-2 text-sm text-slate-600"><span className="font-medium text-slate-700">Expected: </span>{p.expected_result}</p>}
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500 transition-[width]" style={{ width: `${pct}%` }} /></div>
                <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-slate-500">
                  <span>{p.counts.done_tasks}/{p.counts.tasks} tasks done · {p.counts.open_points} point{p.counts.open_points === 1 ? "" : "s"} still to assign</span>
                  <span>{p.ends_on ? `Deadline ${p.ends_on}` : "No deadline set"} · {p.heads && p.heads.length > 0 ? `Heads: ${p.heads.map((h) => h.full_name).join(", ")}` : p.head ? `Head: ${p.head.full_name}` : "No head: assign directly"}{p.qa_members && p.qa_members.length > 0 ? ` · QA: ${p.qa_members.map((q) => q.full_name).join(", ")}` : p.qa ? ` · QA: ${p.qa.full_name}` : ""}</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}

function CreateProject({ onDone, initialCompanyId }: { onDone: () => void; initialCompanyId?: number }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<{ id: number; name: string; code: string }[]>("/companies") });
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>(initialCompanyId ? String(initialCompanyId) : "");
  const emps = useEmployees(selectedCompanyId || null);
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ name: "", description: "", special_note: "", priority: "medium", expected_result: "", starts_on: today, ends_on: "" });
  const [assignee, setAssignee] = useState("");
  const [team, setTeam] = useState<number[]>([]);
  const [selectedHeads, setSelectedHeads] = useState<number[]>([]);
  const [selectedQAs, setSelectedQAs] = useState<number[]>([]);
  const [aiOpen, setAiOpen] = useState(false);
  const [headSearch, setHeadSearch] = useState("");
  const [qaSearch, setQaSearch] = useState("");
  const [points, setPoints] = useState([{ title: "", expected_result: "" }]);
  const [search, setSearch] = useState("");
  const shown = useMemo(() => (emps.data ?? []).filter((e) => e.full_name.toLowerCase().includes(search.toLowerCase())), [emps.data, search]);
  const filteredHeads = useMemo(
    () => (emps.data ?? []).filter((e) => e.full_name.toLowerCase().includes(headSearch.toLowerCase()) || (e.job_title ?? "").toLowerCase().includes(headSearch.toLowerCase())),
    [emps.data, headSearch],
  );
  const filteredQAs = useMemo(
    () => (emps.data ?? []).filter((e) => e.full_name.toLowerCase().includes(qaSearch.toLowerCase()) || (e.job_title ?? "").toLowerCase().includes(qaSearch.toLowerCase())),
    [emps.data, qaSearch],
  );

  const create = useMutation({
    mutationFn: () => api<{ id: number }>("/projects", {
      body: {
        name: f.name, description: f.description || null, expected_result: f.expected_result || null,
        priority: f.priority, special_note: f.special_note || null,
        company_id: selectedCompanyId ? Number(selectedCompanyId) : undefined,
        assignee_id: assignee ? Number(assignee) : null,
        head_employee_id: selectedHeads[0] ?? null,
        sub_head_employee_id: selectedHeads[1] ?? null,
        head_employee_ids: selectedHeads,
        qa_employee_id: selectedQAs[0] ?? null,
        qa_employee_ids: selectedQAs,
        member_ids: team,
        starts_on: f.starts_on || null, ends_on: f.ends_on || null,
        points: points.filter((p) => p.title.trim().length >= 2).map((p) => ({ title: p.title.trim(), expected_result: p.expected_result.trim() || null })),
      },
    }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["projects"] }); qc.invalidateQueries({ queryKey: ["task-meta"] }); onDone(); nav(`/projects/${r.id}`); },
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };
  const toggle = (id: number) => setTeam((t) => (t.includes(id) ? t.filter((x) => x !== id) : [...t, id]));
  const toggleHead = (id: number) => setSelectedHeads((heads) => (heads.includes(id) ? heads.filter((x) => x !== id) : [...heads, id]));
  const toggleQA = (id: number) => setSelectedQAs((qas) => (qas.includes(id) ? qas.filter((x) => x !== id) : [...qas, id]));
  return (
    <Card className="mb-6 p-5">
      <form onSubmit={submit} className="grid gap-5 lg:grid-cols-2">
        <div className="space-y-4">
          {companies.data && companies.data.length > 1 && (
            <Field label="Company">
              <Select value={selectedCompanyId} onChange={(e) => {
                setSelectedCompanyId(e.target.value);
                setAssignee("");
                setTeam([]);
                setSelectedHeads([]);
                setSelectedQAs([]);
              }}>
                <option value="">Default Company</option>
                {companies.data.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
              </Select>
            </Field>
          )}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-slate-700">Project name *</span>
              <button
                type="button"
                onClick={() => setAiOpen(true)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-md bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors shadow-2xs border border-indigo-200 cursor-pointer"
              >
                <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
                Recommend with AI
              </button>
            </div>
            <Input required minLength={2} value={f.name} onChange={set("name")} placeholder="e.g. Elala or HRMS" />
          </div>
          <Field label="What is this project about? (optional)"><textarea rows={3} value={f.description} onChange={set("description")} className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-card focus:border-indigo-500 focus:outline-none focus:ring-4 focus:ring-indigo-100" /></Field>
          <Field label="Special Note (optional)"><textarea rows={2} value={f.special_note} onChange={set("special_note")} className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-card focus:border-indigo-500 focus:outline-none focus:ring-4 focus:ring-indigo-100" placeholder="Special note or instructions..." /></Field>
          <Field label="Priority">
            <Select value={f.priority} onChange={set("priority")}>
              {PRIORITY_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </Select>
          </Field>
          <Field label="Expected result: what should exist when it is finished?"><textarea rows={3} value={f.expected_result} onChange={set("expected_result")} className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-card focus:border-indigo-500 focus:outline-none focus:ring-4 focus:ring-indigo-100" /></Field>
          <Field label="Assign project to employee (optional)">
            <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">No primary assignee</option>
              {emps.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}{e.job_title ? ` · ${e.job_title}` : ""}</option>)}
            </Select>
          </Field>
          <div>
            <div className="mb-1 text-xs font-medium text-slate-700">Project Heads ({selectedHeads.length} selected, multiple heads supported)</div>
            <Input
              placeholder="Search heads / sub-heads..."
              value={headSearch}
              onChange={(e) => setHeadSearch(e.target.value)}
              className="text-xs py-1 mb-1.5"
            />
            <div className="max-h-32 overflow-y-auto rounded-lg border border-hairline p-1">
              {filteredHeads.map((e) => (
                <label key={e.id} className="flex cursor-pointer items-center gap-2 px-2 py-1 text-sm hover:bg-slate-50">
                  <input type="checkbox" checked={selectedHeads.includes(e.id)} onChange={() => toggleHead(e.id)} />
                  <span>{e.full_name} <span className="text-xs text-slate-400">· {e.job_title}</span></span>
                </label>
              ))}
              {filteredHeads.length === 0 && <p className="p-1 text-xs text-slate-400">No matching heads.</p>}
            </div>
            <p className="mt-1 text-xs text-slate-500">If no head is selected, it falls back to the employee's department head and sub-head.</p>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-slate-700">Assigned QA members ({selectedQAs.length} selected, optional)</div>
            <Input
              placeholder="Search QA members..."
              value={qaSearch}
              onChange={(e) => setQaSearch(e.target.value)}
              className="text-xs py-1 mb-1.5"
            />
            <div className="max-h-32 overflow-y-auto rounded-lg border border-hairline p-1">
              {filteredQAs.map((e) => (
                <label key={e.id} className="flex cursor-pointer items-center gap-2 px-2 py-1 text-sm hover:bg-slate-50">
                  <input type="checkbox" checked={selectedQAs.includes(e.id)} onChange={() => toggleQA(e.id)} />
                  <span>{e.full_name} <span className="text-xs text-slate-400">· {e.job_title}</span></span>
                </label>
              ))}
              {filteredQAs.length === 0 && <p className="p-1 text-xs text-slate-400">No matching QA testers.</p>}
            </div>
            <p className="mt-1 text-xs text-slate-500">Multiple QA members can be assigned and share one unified testing status.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Start date"><Input type="date" value={f.starts_on} onChange={set("starts_on")} /></Field>
            <Field label="Project deadline (required)"><Input required type="date" min={f.starts_on || today} value={f.ends_on} onChange={set("ends_on")} /></Field>
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <div className="mb-1.5 flex items-center justify-between"><span className="text-xs font-medium text-slate-700">Team ({team.length} selected, optional)</span></div>
            <Input placeholder="Search people" value={search} onChange={(e) => setSearch(e.target.value)} />
            <div className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-hairline">
              {emps.isLoading && <Spinner />}
              {shown.map((e) => (
                <label key={e.id} className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-slate-50">
                  <input type="checkbox" checked={team.includes(e.id)} onChange={() => toggle(e.id)} /> {e.full_name} <span className="text-xs text-slate-400">{e.job_title}</span>
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-slate-500">With a team, tasks can only go to team members. Leave empty to choose anyone.</p>
          </div>
          <div>
            <span className="text-xs font-medium text-slate-700">Project points (checklist / scope items)</span>
            <div className="mt-1.5 space-y-2">
              {points.map((p, i) => (
                <div key={i} className="flex gap-2">
                  <Input placeholder={`Point ${i + 1}`} value={p.title} onChange={(e) => setPoints(points.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
                  <Input placeholder="Expected result (optional)" value={p.expected_result} onChange={(e) => setPoints(points.map((x, j) => (j === i ? { ...x, expected_result: e.target.value } : x)))} />
                  {points.length > 1 && <Button type="button" variant="ghost" aria-label="Remove point" onClick={() => setPoints(points.filter((_, j) => j !== i))}><Trash2 size={16} /></Button>}
                </div>
              ))}
            </div>
            <Button type="button" variant="ghost" className="mt-2" onClick={() => setPoints([...points, { title: "", expected_result: "" }])}><Plus size={16} /> Add another point</Button>
            <p className="text-xs text-slate-500">You can add more points later and assign each one when you are ready.</p>
          </div>
        </div>
        <div className="flex items-center gap-3 lg:col-span-2"><Button type="submit" disabled={create.isPending}>Create project</Button><ErrorNote error={create.error} /></div>
      </form>

      <AiAssistModal
        isOpen={aiOpen}
        onClose={() => setAiOpen(false)}
        title={f.name}
        companyId={selectedCompanyId ? Number(selectedCompanyId) : 1}
        priority={f.priority}
        targetType="project"
        existingDescription={f.description}
        existingSpecialNote={f.special_note}
        onApply={(desc, note) => {
          setF((prev) => ({ ...prev, description: desc, special_note: note }));
        }}
        onApplyDescription={(desc) => setF((prev) => ({ ...prev, description: desc }))}
        onApplySpecialNote={(note) => setF((prev) => ({ ...prev, special_note: note }))}
      />
    </Card>
  );
}
