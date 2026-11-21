import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { LevelBadge, LoadBar, PriorityCounts, type Workload } from "@/components/task-ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** How much work each person carries. Owner/CEO see everyone, the Manager their team, a head their department. */
export function WorkloadPage() {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["workload"], queryFn: () => api<Workload[]>("/workload") });
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("");
  const depts = useMemo(() => [...new Set(q.data?.map((w) => w.department).filter(Boolean) as string[])].sort(), [q.data]);
  const rows = (q.data ?? []).filter((w) => (!dept || w.department === dept) && w.full_name.toLowerCase().includes(search.toLowerCase()));
  const totals = rows.reduce((a, w) => ({ open: a.open + w.open_tasks, overdue: a.overdue + w.overdue_tasks }), { open: 0, overdue: 0 });

  return (
    <>
      <PageHeader title="Team workload" subtitle="Open tasks per person, how urgent they are, and how loaded each person is over the next 7 working days." />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Card className="p-4"><div className="text-xs text-slate-500">People</div><div className="text-2xl font-semibold">{rows.length}</div></Card>
        <Card className="p-4"><div className="text-xs text-slate-500">Open tasks</div><div className="text-2xl font-semibold">{totals.open}</div></Card>
        <Card className="p-4"><div className="text-xs text-slate-500">Overdue</div><div className={`text-2xl font-semibold ${totals.overdue ? "text-red-600" : ""}`}>{totals.overdue}</div></Card>
      </div>
      <div className="mb-4 flex flex-wrap gap-3">
        <Input className="max-w-xs" placeholder="Search people" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select className="max-w-xs" value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">All departments</option>
          {depts.map((d) => <option key={d}>{d}</option>)}
        </Select>
      </div>
      <Card className="overflow-x-auto">
        {q.isLoading ? <Spinner /> : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="p-3">Person</th><th className="p-3">Open</th>
                <th className="p-3" title="Critical / High / Medium / Low">C · H · M · L</th>
                <th className="p-3">Overdue</th><th className="p-3">Due ≤ 7 days</th><th className="p-3">Load</th><th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {rows.map((w) => (
                <tr key={w.employee_id} className="border-b border-slate-100 last:border-0">
                  <td className="p-3">
                    <div className="font-medium">{w.full_name} {w.is_me && <Badge>You</Badge>} {w.on_leave && <Badge tone="orange">On leave</Badge>}</div>
                    <div className="text-xs text-slate-500">{w.job_title ?? "—"} · {w.department}</div>
                  </td>
                  <td className="p-3 text-base font-semibold">{w.open_tasks}</td>
                  <td className="p-3"><PriorityCounts c={w.by_priority} /></td>
                  <td className="p-3">{w.overdue_tasks ? <span className="font-semibold text-red-600">{w.overdue_tasks}</span> : <span className="text-slate-400">0</span>}</td>
                  <td className="p-3">{w.due_next_7_days}</td>
                  <td className="p-3">
                    <div className="flex items-center gap-2"><LoadBar pct={w.load_pct} /><LevelBadge level={w.level} /></div>
                    <div className="mt-0.5 text-xs text-slate-500">{w.next7_estimated_hours}h of {w.capacity_hours_next_7_days}h</div>
                  </td>
                  <td className="whitespace-nowrap p-3 text-right">
                    <Link to={`/tasks?assignee_id=${w.employee_id}`}><Button variant="ghost">View tasks</Button></Link>
                    {can("task.create") && !w.is_me && <Link to={`/tasks/new?assignee=${w.employee_id}`}><Button variant="outline">Assign</Button></Link>}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-slate-500">No people match.</td></tr>}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
