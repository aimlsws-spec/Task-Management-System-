import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDay, PriorityChip } from "@/components/task-ui";
import { useAuth } from "@/lib/auth";

export type Overview = {
  scope: string; scope_label: string;
  totals: { all: number; open: number; overdue: number; due_next_7_days: number; completed_last_7_days: number; completed_total: number; open_blockers: number; on_time_pct: number | null };
  by_status: Record<string, number>; by_priority: Record<string, number>;
  by_department: { department_id: number; department: string; open: number; overdue: number; completed: number; on_time_pct: number | null }[];
  by_person: { employee_id: number; full_name: string; open: number; overdue: number; completed: number }[];
  top_overdue: { task_id: number; task_no: string; title: string; assignee: string; priority: string; due_at: string; extension_count: number; explanation_required: boolean }[];
  needs_my_decision?: { explanations: number; overdue_without_reason: number };
};

const BAR: Record<string, string> = { critical: "bg-red-500", high: "bg-orange-500", medium: "bg-amber-400", low: "bg-slate-400" };

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold ${tone ?? ""}`}>{value}</div>
    </div>
  );
}

function Bars({ data, colors }: { data: [string, number][]; colors?: Record<string, string> }) {
  const max = Math.max(1, ...data.map(([, n]) => n));
  return (
    <ul className="space-y-1.5">
      {data.map(([k, n]) => (
        <li key={k} className="flex items-center gap-2 text-xs">
          <span className="w-24 shrink-0 capitalize text-slate-600">{k.replace("_", " ")}</span>
          <span className="h-3 flex-1 rounded bg-slate-100"><span className={`block h-3 rounded ${colors?.[k] ?? "bg-indigo-500"}`} style={{ width: `${(n / max) * 100}%` }} /></span>
          <span className="w-8 text-right tabular-nums">{n}</span>
        </li>
      ))}
    </ul>
  );
}

/** Company / team / department summary for whoever is signed in; the breadth is decided by the server (their scope). */
export function OverviewPanel() {
  const { me } = useAuth();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Overview>("/dashboard") });
  if (!q.data) return null;
  const d = q.data;
  const t = d.totals;
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Overview · {d.scope_label}</h2>
        <Link to="/reports" className="text-xs text-indigo-600 hover:underline">All reports & exports →</Link>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Open tasks" value={t.open} />
        <Stat label="Overdue" value={t.overdue} tone={t.overdue ? "text-red-700" : ""} />
        <Stat label="Due in 7 days" value={t.due_next_7_days} />
        <Stat label="Open blockers" value={t.open_blockers} tone={t.open_blockers ? "text-orange-700" : ""} />
        <Stat label="Completed (7 days)" value={t.completed_last_7_days} />
        <Stat label="Completed (all)" value={t.completed_total} />
        <Stat label="On time" value={t.on_time_pct == null ? "–" : `${t.on_time_pct}%`} />
        {d.needs_my_decision && <Stat label="Delay reasons to decide" value={d.needs_my_decision.explanations} tone={d.needs_my_decision.explanations ? "text-orange-700" : ""} />}
      </div>
      <div className="mt-4 grid gap-5 md:grid-cols-2">
        <div><h3 className="mb-2 text-xs font-semibold uppercase text-slate-400">Open tasks by priority</h3><Bars data={Object.entries(d.by_priority)} colors={BAR} /></div>
        <div><h3 className="mb-2 text-xs font-semibold uppercase text-slate-400">All tasks by status</h3><Bars data={Object.entries(d.by_status).filter(([, n]) => n > 0)} /></div>
      </div>
      {d.by_department.length > 1 && (
        <div className="mt-4 overflow-x-auto">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-400">By department</h3>
          <table data-no-stack className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500"><tr><th className="py-1">Department</th><th>Open</th><th>Overdue</th><th>Completed</th><th>On time</th></tr></thead>
            <tbody>{d.by_department.map((r) => <tr key={r.department_id} className="border-t border-slate-100"><td className="py-1.5">{r.department}</td><td>{r.open}</td><td className={r.overdue ? "text-red-700" : ""}>{r.overdue}</td><td>{r.completed}</td><td>{r.on_time_pct == null ? "–" : `${r.on_time_pct}%`}</td></tr>)}</tbody>
          </table>
        </div>
      )}
      {d.top_overdue.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-400">Most urgent overdue</h3>
          <ul className="divide-y divide-slate-100 text-sm">
            {d.top_overdue.map((o) => (
              <li key={o.task_id} className="flex flex-wrap items-center gap-2 py-1.5">
                <Link to={`/tasks/${o.task_id}`} className="font-medium hover:underline">{o.title}</Link>
                <span className="text-xs text-slate-500">{o.assignee} · due {fmtDay(o.due_at, me?.user.timezone)}</span>
                <PriorityChip priority={o.priority} />
                {o.extension_count > 0 && <Badge tone="orange">Extended ×{o.extension_count}</Badge>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
