import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { fmtDay, LevelBadge, LoadBar, OverdueBadge, PriorityChip, PriorityCounts, StatusBadge, type Task, type TaskPage, type Workload } from "@/components/task-ui";
import { AiAssistModal } from "@/components/AiAssistModal";
import { useEmployees } from "@/pages/Projects";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Meta = {
  categories: { id: number; name: string }[];
  types: { id: number; name: string; requires_review: boolean }[];
  projects: { id: number; code: string; name: string; company_id?: number }[];
};

/** Pick a person from the list (with their current load), then describe and assign the task. */
export function NewTask() {
  const nav = useNavigate();
  const { me } = useAuth();
  const [sp] = useSearchParams();
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<{ id: number; name: string; code: string }[]>("/companies") });
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>("");
  const [assignee, setAssignee] = useState<number | null>(sp.get("assignee") ? Number(sp.get("assignee")) : null);
  const [search, setSearch] = useState("");
  const [headSearch, setHeadSearch] = useState("");
  const [qaSearch, setQaSearch] = useState("");
  const [selectedHeads, setSelectedHeads] = useState<number[]>([]);
  const [selectedQAs, setSelectedQAs] = useState<number[]>([]);
  const [aiOpen, setAiOpen] = useState(false);
  const [f, setF] = useState({
    title: "", description: "", instructions: "", priority: "medium", due_date: "", start_date: today,
    project_id: sp.get("project_id") || "", category_id: "", type_id: "",
  });

  const meta = useQuery({
    queryKey: ["task-meta", selectedCompanyId],
    queryFn: () => api<Meta>("/task-meta", { params: { company_id: selectedCompanyId || undefined } }),
  });

  const selectedProj = meta.data?.projects.find((p) => String(p.id) === f.project_id);
  const effectiveCompanyId = selectedProj?.company_id ? String(selectedProj.company_id) : selectedCompanyId;

  const people = useQuery({
    queryKey: ["workload", effectiveCompanyId],
    queryFn: () => api<Workload[]>("/workload", { params: { company_id: effectiveCompanyId || undefined } }),
  });
  const chosen = people.data?.find((p) => p.employee_id === assignee);
  const theirTasks = useQuery({
    queryKey: ["tasks", "of", assignee],
    queryFn: () => api<TaskPage>("/tasks", { params: { assignee_id: assignee, open: "true", page_size: 8 } }),
    enabled: assignee !== null,
  });
  const everyone = useEmployees(effectiveCompanyId || null);
  const loopPeople = useMemo(() => {
    const seen = new Map<number, { id: number; full_name: string; job_title: string | null }>();
    for (const e of everyone.data ?? []) seen.set(e.id, e);
    for (const w of people.data ?? []) if (!seen.has(w.employee_id)) seen.set(w.employee_id, { id: w.employee_id, full_name: w.full_name, job_title: w.job_title });
    return [...seen.values()].filter((e) => e.id !== assignee).sort((a, b) => a.full_name.localeCompare(b.full_name));
  }, [everyone.data, people.data, assignee]);
  const list = useMemo(
    () => (people.data ?? []).filter((p) => !p.is_me && p.full_name.toLowerCase().includes(search.toLowerCase())),
    [people.data, search],
  );

  const filteredHeads = useMemo(
    () => loopPeople.filter((p) => p.full_name.toLowerCase().includes(headSearch.toLowerCase()) || (p.job_title ?? "").toLowerCase().includes(headSearch.toLowerCase())),
    [loopPeople, headSearch],
  );
  const filteredQAs = useMemo(
    () => loopPeople.filter((p) => p.full_name.toLowerCase().includes(qaSearch.toLowerCase()) || (p.job_title ?? "").toLowerCase().includes(qaSearch.toLowerCase())),
    [loopPeople, qaSearch],
  );

  const toggleHead = (id: number) => {
    setSelectedHeads((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleQA = (id: number) => {
    setSelectedQAs((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const create = useMutation({
    mutationFn: () =>
      api<{ task: Task; warnings: string[] }>("/tasks", {
        body: {
          title: f.title, description: f.description, instructions: f.instructions || null, special_note: f.instructions || null, assignee_id: assignee,
          company_id: effectiveCompanyId ? Number(effectiveCompanyId) : undefined,
          priority: f.priority, due_date: f.due_date || null, start_date: f.start_date || today,
          project_id: f.project_id ? Number(f.project_id) : null,
          category_id: f.category_id ? Number(f.category_id) : null, type_id: f.type_id ? Number(f.type_id) : null,
          head_employee_id: selectedHeads[0] ?? null,
          sub_head_employee_id: selectedHeads[1] ?? null,
          head_employee_ids: selectedHeads,
          qa_employee_id: selectedQAs[0] ?? null,
          qa_employee_ids: selectedQAs,
        },
      }),
    onSuccess: (r) => nav(`/tasks/${r.task.id}`, { state: { warnings: r.warnings, created: true } }),
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); if (assignee) create.mutate(); };

  return (
    <>
      <PageHeader title="Assign a task" subtitle="Choose who it goes to — you can see how much each person already has. They are notified through their task list and the activity trail." />
      <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
        {/* 1. People */}
        <Card className="h-fit p-3">
          {companies.data && companies.data.length > 1 && (
            <div className="mb-2.5 pb-2 border-b border-slate-100">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-400 block mb-1">Company</label>
              <Select
                value={selectedCompanyId}
                onChange={(e) => {
                  setSelectedCompanyId(e.target.value);
                  setAssignee(null);
                  setSelectedHeads([]);
                  setSelectedQAs([]);
                }}
              >
                <option value="">All / Default Company</option>
                {companies.data.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.code})
                  </option>
                ))}
              </Select>
            </div>
          )}
          <div className="px-1 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">1 · Assign to</div>
          <Input placeholder="Search people" value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="mt-2 max-h-[34rem] space-y-1.5 overflow-y-auto pr-1">
            {people.isLoading && <Spinner />}
            {list.map((p) => (
              <button
                key={p.employee_id} type="button" onClick={() => setAssignee(p.employee_id)}
                className={cn("w-full rounded-lg border p-2.5 text-left transition-colors", assignee === p.employee_id ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:bg-slate-50")}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{p.full_name}</span>
                  <LevelBadge level={p.level} />
                </div>
                <div className="text-xs text-slate-500">{p.job_title ?? "—"} · {p.department}</div>
                <div className="mt-1.5 flex items-center gap-2 text-xs text-slate-600">
                  <span><b>{p.open_tasks}</b> open</span>
                  {p.overdue_tasks > 0 && <span className="font-semibold text-red-600">{p.overdue_tasks} overdue</span>}
                  <PriorityCounts c={p.by_priority} />
                  <LoadBar pct={p.load_pct} />
                </div>
              </button>
            ))}
            {!people.isLoading && list.length === 0 && <p className="p-3 text-sm text-slate-500">No one matches.</p>}
          </div>
        </Card>

        {/* 2. Details */}
        <div className="space-y-5">
          {chosen && (
            <Card className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div><span className="font-semibold">{chosen.full_name}</span> <span className="text-sm text-slate-500">· current workload</span></div>
                <LevelBadge level={chosen.level} />
              </div>
              <div className="mt-2 grid gap-3 text-sm sm:grid-cols-3">
                <div><div className="text-xs text-slate-500">Open tasks</div><div className="text-lg font-semibold">{chosen.open_tasks}</div></div>
                <div><div className="text-xs text-slate-500">Overdue</div><div className={cn("text-lg font-semibold", chosen.overdue_tasks && "text-red-600")}>{chosen.overdue_tasks}</div></div>
                <div><div className="text-xs text-slate-500">Priorities (C·H·M·L)</div><PriorityCounts c={chosen.by_priority} /></div>
              </div>
              {chosen.level !== "normal" && <p className="mt-3 rounded-lg bg-orange-50 px-3 py-2 text-sm text-orange-800">{chosen.full_name} is already {chosen.level === "high" ? "heavily loaded" : "over capacity"} for the next 7 days. Consider a different deadline or person.</p>}
              {theirTasks.data && theirTasks.data.items.length > 0 && (
                <ul className="mt-3 divide-y divide-slate-100 text-sm">
                  {theirTasks.data.items.map((t) => (
                    <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                      <span className="min-w-0 truncate">{t.title} <span className="text-xs text-slate-400">{t.task_no}</span></span>
                      <span className="flex items-center gap-1.5"><PriorityChip priority={t.priority} /><StatusBadge status={t.status} />{t.is_overdue && <OverdueBadge />}<span className="text-xs text-slate-500">{fmtDay(t.due_at, me?.user.timezone)}</span></span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}

          <Card className="p-5">
            <div className="pb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">2 · Task details</div>
            <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-medium text-slate-700">Task title *</span>
                  <button
                    type="button"
                    onClick={() => setAiOpen(true)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-md bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors shadow-2xs border border-indigo-200 cursor-pointer"
                  >
                    <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
                    Recommend with AI
                  </button>
                </div>
                <Input required minLength={3} maxLength={200} value={f.title} onChange={set("title")} placeholder="e.g. Elala UI changes or HRMS employee attendance" />
              </div>
              <div className="sm:col-span-2"><Field label="Description"><textarea required minLength={3} rows={4} value={f.description} onChange={set("description")} className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200" /></Field></div>
              <div className="sm:col-span-2"><Field label="Special Note (optional)"><textarea rows={2} value={f.instructions} onChange={set("instructions")} className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200" placeholder="Special notes or instructions..." /></Field></div>
              <Field label="Priority">
                <Select value={f.priority} onChange={set("priority")}>
                  {["critical", "high", "medium", "low"].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
                </Select>
              </Field>
              <Field label={f.project_id ? "Deadline date (optional — inherits project deadline)" : "Deadline date"}><Input required={!f.project_id} type="date" value={f.due_date} onChange={set("due_date")} /></Field>
              <Field label="Start date (defaults to today, editable)"><Input type="date" value={f.start_date} onChange={set("start_date")} /></Field>
              <Field label="Project (optional)">
                <Select
                  value={f.project_id}
                  onChange={(e) => {
                    const pid = e.target.value;
                    setF({ ...f, project_id: pid });
                    if (pid) {
                      const pr = meta.data?.projects.find((x) => String(x.id) === pid);
                      if (pr?.company_id) {
                        setSelectedCompanyId(String(pr.company_id));
                      }
                    }
                  }}
                >
                  <option value="">None</option>
                  {meta.data?.projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      [{p.code}] {p.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Category">
                <Select value={f.category_id} onChange={set("category_id")}><option value="">None</option>{meta.data?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
              </Field>
              <Field label="Task type">
                <Select value={f.type_id} onChange={set("type_id")}><option value="">None</option>{meta.data?.types.map((t) => <option key={t.id} value={t.id}>{t.name}{t.requires_review ? " (needs review)" : ""}</option>)}</Select>
              </Field>
              <div className="sm:col-span-2">
                <Field label={`Project / Responsible Heads (optional, ${selectedHeads.length} selected — multiple heads supported)`}>
                  <div className="space-y-1.5">
                    <Input
                      placeholder="Search heads / sub-heads..."
                      value={headSearch}
                      onChange={(e) => setHeadSearch(e.target.value)}
                      className="text-xs py-1"
                    />
                    <div className="max-h-36 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1">
                      {filteredHeads.map((e) => (
                        <label key={e.id} className="flex items-center gap-2 text-xs text-slate-700 hover:bg-slate-50 p-1 rounded cursor-pointer">
                          <input
                            type="checkbox"
                            checked={selectedHeads.includes(e.id)}
                            onChange={() => toggleHead(e.id)}
                            className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span>{e.full_name}{e.job_title ? ` · ${e.job_title}` : ""}</span>
                        </label>
                      ))}
                      {filteredHeads.length === 0 && <p className="p-1 text-xs text-slate-400">No matching heads.</p>}
                    </div>
                    <p className="text-xs text-slate-500">
                      Select 1 or more Heads / SubHeads. If none are selected, the department Head and SubHead of the assigned employee will automatically be in loop as fallback.
                    </p>
                  </div>
                </Field>
              </div>

              <div className="sm:col-span-2">
                <Field label={`QA Testers (optional, ${selectedQAs.length} selected — multiple QA members share one testing status)`}>
                  <div className="space-y-1.5">
                    <Input
                      placeholder="Search QA members..."
                      value={qaSearch}
                      onChange={(e) => setQaSearch(e.target.value)}
                      className="text-xs py-1"
                    />
                    <div className="max-h-36 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1">
                      {filteredQAs.map((e) => (
                        <label key={e.id} className="flex items-center gap-2 text-xs text-slate-700 hover:bg-slate-50 p-1 rounded cursor-pointer">
                          <input
                            type="checkbox"
                            checked={selectedQAs.includes(e.id)}
                            onChange={() => toggleQA(e.id)}
                            className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span>{e.full_name}{e.job_title ? ` · ${e.job_title}` : ""}</span>
                        </label>
                      ))}
                      {filteredQAs.length === 0 && <p className="p-1 text-xs text-slate-400">No matching QA testers.</p>}
                    </div>
                  </div>
                </Field>
              </div>
              <p className="-mt-2 text-xs text-slate-500 sm:col-span-2">When the assignee finishes: multiple QA members share one testing stage (any QA member can test and sign off or report defects), then any assigned Head or SubHead approves, then Owner or CEO completes it. If neither Head nor SubHead is selected, fallback uses department leadership; if department has neither, it is a specific employee task.</p>
              <div className="sm:col-span-2 flex items-center gap-3 border-t border-slate-100 pt-4">
                <Button type="submit" disabled={!assignee || create.isPending}>{create.isPending ? "Assigning…" : chosen ? `Assign to ${chosen.full_name}` : "Choose a person first"}</Button>
                <Badge>Assigned by you</Badge>
              </div>
              <div className="sm:col-span-2"><ErrorNote error={create.error} /></div>
            </form>
          </Card>
        </div>
      </div>

      <AiAssistModal
        isOpen={aiOpen}
        onClose={() => setAiOpen(false)}
        title={f.title}
        companyId={effectiveCompanyId ? Number(effectiveCompanyId) : 1}
        priority={f.priority}
        targetType="task"
        existingDescription={f.description}
        existingSpecialNote={f.instructions}
        onApply={(desc, note) => {
          setF((prev) => ({ ...prev, description: desc, instructions: note }));
        }}
        onApplyDescription={(desc) => setF((prev) => ({ ...prev, description: desc }))}
        onApplySpecialNote={(note) => setF((prev) => ({ ...prev, instructions: note }))}
      />
    </>
  );
}
