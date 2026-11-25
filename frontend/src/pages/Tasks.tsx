import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { EscalationBadge, fmtDay, OverdueBadge, PriorityChip, PRIORITY_OPTIONS, STATUS_OPTIONS, StatusBadge, type TaskPage, type Workload } from "@/components/task-ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function Tasks() {
  const { me, can } = useAuth();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const get = (k: string) => sp.get(k) ?? "";
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    if (v) n.set(k, v); else n.delete(k);
    n.delete("page");
    setSp(n, { replace: true });
  };
  const page = Number(get("page") || 1);
  const isAssigner = can("task.assign");
  const tz = me?.user.timezone;

  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<{ id: number; name: string; code: string }[]>("/companies") });
  const people = useQuery({
    queryKey: ["workload", get("company_id")],
    queryFn: () => api<Workload[]>("/workload", { params: { company_id: get("company_id") || undefined } }),
    enabled: isAssigner,
  });
  const tasks = useQuery({
    queryKey: ["tasks", sp.toString()],
    refetchInterval: 6000,
    queryFn: () =>
      api<TaskPage>("/tasks", {
        params: { status: get("status"), priority: get("priority"), assignee_id: get("assignee_id"), company_id: get("company_id") || undefined, q: get("q"), page, page_size: 25,
                  overdue: get("overdue") || undefined, open: get("open") || undefined, awaiting_my_review: get("awaiting_my_review") || undefined },
      }),
  });
  const self = me?.permissions["task.view"] === "self";

  return (
    <>
      <PageHeader
        title={self ? "My tasks" : "Tasks"}
        subtitle={self ? "Most urgent first: overdue, then priority, then deadline." : "Everything in your scope, most urgent first."}
        actions={can("task.create") && can("task.assign") ? <Link to="/tasks/new"><Button>Assign task</Button></Link> : undefined}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input className="sm:max-w-56" placeholder="Search tasks..." value={get("q")} onChange={(e) => set("q", e.target.value)} />
        {companies.data && companies.data.length > 1 && (
          <Select className="sm:max-w-44" value={get("company_id")} onChange={(e) => set("company_id", e.target.value)}>
            <option value="">All companies</option>
            {companies.data.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
          </Select>
        )}
        <Select className="sm:max-w-40" value={get("status")} onChange={(e) => set("status", e.target.value)}>
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </Select>
        <Select className="sm:max-w-36" value={get("priority")} onChange={(e) => set("priority", e.target.value)}>
          <option value="">All priorities</option>
          {PRIORITY_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </Select>
        {isAssigner && (
          <Select className="sm:max-w-48" value={get("assignee_id")} onChange={(e) => set("assignee_id", e.target.value)}>
            <option value="">Everyone</option>
            {people.data?.map((p) => <option key={p.employee_id} value={p.employee_id}>{p.full_name}</option>)}
          </Select>
        )}
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={get("open") === "true"} onChange={(e) => set("open", e.target.checked ? "true" : "")} /> Open only</label>
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={get("awaiting_my_review") === "true"} onChange={(e) => set("awaiting_my_review", e.target.checked ? "true" : "")} /> Waiting for my review</label>
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={get("overdue") === "true"} onChange={(e) => set("overdue", e.target.checked ? "true" : "")} /> Overdue only</label>
      </div>
      <Card className="overflow-x-auto">
        {tasks.isLoading ? <Spinner /> : (<>
          <ul className="divide-y divide-slate-100 md:hidden">
            {tasks.data?.items.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => nav(`/tasks/${t.id}`)} className="block w-full space-y-2 p-4 text-left active:bg-slate-50">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 font-medium">{t.title}</div>
                    <PriorityChip priority={t.priority} />
                  </div>
                  <div className="text-xs text-slate-500">{t.task_no}{t.company ? ` · [${t.company.code || t.company.name}]` : ""} · by {t.assigned_by.full_name}{!self && <> · {t.assignee.full_name}</>}</div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge status={t.status} />{t.is_overdue && <OverdueBadge />}{t.explanation_required && <Badge tone="red">Explanation needed</Badge>}{!self && <EscalationBadge level={t.escalation_level} />}
                    <span className="ml-auto text-xs text-slate-600">Due {fmtDay(t.due_at, tz)}</span>
                  </div>
                </button>
              </li>
            ))}
            {tasks.data?.items.length === 0 && <li className="p-8 text-center text-slate-500">No tasks match these filters.</li>}
          </ul>
          <table className="hidden w-full text-left text-sm md:table">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="p-3">Task</th>{!self && <th className="p-3">Assignee</th>}<th className="p-3">Priority</th><th className="p-3">Status</th><th className="p-3">Deadline</th></tr>
            </thead>
            <tbody>
              {tasks.data?.items.map((t) => (
                <tr key={t.id} onClick={() => nav(`/tasks/${t.id}`)} className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{t.title}</span>
                      {t.company && (
                        <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 border border-indigo-200">
                          {t.company.code || t.company.name}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">{t.task_no} · by {t.assigned_by.full_name}</div>
                  </td>
                  {!self && <td className="p-3"><div>{t.assignee.full_name}</div><div className="text-xs text-slate-500">{t.assignee.job_title}</div></td>}
                  <td className="p-3"><PriorityChip priority={t.priority} /></td>
                  <td className="p-3"><div className="flex flex-wrap gap-1"><StatusBadge status={t.status} />{t.is_overdue && <OverdueBadge />}{t.explanation_required && <Badge tone="red">Explanation needed</Badge>}{!self && <EscalationBadge level={t.escalation_level} />}</div></td>
                  <td className="whitespace-nowrap p-3">{fmtDay(t.due_at, tz)}</td>
                </tr>
              ))}
              {tasks.data?.items.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-slate-500">No tasks match these filters.</td></tr>}
            </tbody>
          </table>
        </>)}
      </Card>
      {tasks.data && tasks.data.total > tasks.data.page_size && (
        <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
          <span>{tasks.data.total} tasks</span>
          <div className="flex gap-2">
            <Button variant="outline" disabled={page <= 1} onClick={() => set("page", String(page - 1))}>Previous</Button>
            <Button variant="outline" disabled={page * tasks.data.page_size >= tasks.data.total} onClick={() => set("page", String(page + 1))}>Next</Button>
          </div>
        </div>
      )}
    </>
  );
}
