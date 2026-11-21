import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card, PageHeader } from "@/components/ui";
import { fmtDay, LevelBadge, OverdueBadge, PriorityChip, StatusBadge, type DelayQueue, type TaskPage, type Workload } from "@/components/task-ui";
import { OverviewPanel } from "@/components/Overview";
import { AdminDashboard } from "@/components/AdminDashboard";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Employee-first "My Day". People who assign work also get a short "needs your attention" list. */
export function Dashboard() {
  const { me, can } = useAuth();
  const name = me?.employee?.full_name ?? me?.user.email;
  if (!can("task.view")) {
    return <AdminDashboard name={name} />;
  }
  return (
    <>
      <PageHeader title={`Welcome, ${name?.split(" ")[0]}`} subtitle="Here is what needs you today." />
      <div className="space-y-5">
        <ReviewWaiting />
        {can("task.assign") && <Attention />}
        {me?.permissions["task.view"] !== "self" && <OverviewPanel />}
        <MyDay />
      </div>
    </>
  );
}

/** Project work whose review turn is mine: the project head's approvals, and the CEO's / Owner's final reviews. */
function ReviewWaiting() {
  const { me } = useAuth();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["tasks", "awaiting-my-review"], queryFn: () => api<TaskPage>("/tasks", { params: { awaiting_my_review: "true", page_size: 8 } }), refetchInterval: 6000 });
  if (!q.data?.items.length) return null;
  const tz = me?.user.timezone;
  return (
    <Card className="border-violet-200 bg-violet-50/60 p-5">
      <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold text-violet-900">Work waiting for your testing or review ({q.data.total})</h2><Link to="/tasks?awaiting_my_review=true" className="text-xs font-medium text-violet-700 hover:underline">See all</Link></div>
      <ul className="divide-y divide-violet-100 text-sm">
        {q.data.items.map((t) => (
          <li key={t.id} onClick={() => nav(`/tasks/${t.id}`)} className="flex cursor-pointer flex-wrap items-center gap-3 py-2 hover:bg-violet-50">
            <span className="min-w-0 flex-1 truncate font-medium">{t.title} <span className="text-xs font-normal text-slate-400">{t.task_no}</span></span>
            <span className="text-xs text-slate-500">by {t.assignee.full_name}</span>
            <Badge tone="purple">{t.review_stage === "qa" ? "Your testing" : t.review_stage === "head" ? "Your approval" : "CEO / Owner review"}</Badge>
            <span className="whitespace-nowrap text-xs text-slate-500">{fmtDay(t.due_at, tz)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Attention() {
  const { can } = useAuth();
  const review = useQuery({ queryKey: ["tasks", "attn", "review"], queryFn: () => api<TaskPage>("/tasks", { params: { status: "under_review", page_size: 1 } }) });
  const overdue = useQuery({ queryKey: ["tasks", "attn", "overdue"], queryFn: () => api<TaskPage>("/tasks", { params: { overdue: "true", page_size: 1 } }) });
  const delays = useQuery({ queryKey: ["delays", "queue"], queryFn: () => api<DelayQueue>("/delays/queue"), enabled: can("delay.review") });
  const blockers = useQuery({ queryKey: ["blockers", ""], queryFn: () => api<{ total: number }>("/blockers"), enabled: can("blocker.manage") });
  const exts = useQuery({ queryKey: ["extension-requests"], queryFn: () => api<unknown[]>("/extension-requests"), enabled: can("task.deadline.edit") });
  const accent = { red: "bg-red-500", purple: "bg-violet-500", orange: "bg-orange-500" } as const;
  const item = (to: string, n: number | undefined, label: string, tone: "red" | "purple" | "orange") => (
    <Link to={to} className="group relative flex items-center justify-between gap-3 overflow-hidden rounded-xl border border-hairline bg-white p-4 pl-5 transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-pop">
      <span aria-hidden className={`absolute inset-y-0 left-0 w-1 ${n ? accent[tone] : "bg-slate-200"}`} />
      <span className="text-sm text-slate-600 group-hover:text-slate-900">{label}</span>
      <span className={`text-2xl font-semibold tabular-nums tracking-tight ${n ? "text-slate-900" : "text-slate-300"}`}>{n ?? "…"}</span>
    </Link>
  );
  return (
    <Card className="p-5">
      <h2 className="mb-4 text-sm font-semibold text-brand-ink">Needs your attention</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {item("/tasks?overdue=true", overdue.data?.total, "Overdue tasks", "red")}
        {item("/tasks?status=under_review", review.data?.total, "Waiting for your review", "purple")}
        {can("blocker.manage") && item("/blockers", blockers.data?.total, "Open blockers", "orange")}
        {can("delay.review") && item("/delays", delays.data?.missing.length, "Overdue with no explanation", "red")}
        {can("delay.review") && item("/delays", delays.data?.awaiting.length, "Explanations to decide on", "orange")}
        {can("task.deadline.edit") && item("/delays", exts.data?.length, "Extension requests", "purple")}
      </div>
      <p className="mt-3 text-xs text-slate-500">See who is carrying what in <Link to="/workload" className="text-indigo-600 hover:underline">Team workload</Link>.</p>
    </Card>
  );
}

/** "My work" at a glance: who I report to, and how many tasks / projects I have, done and not done. */
function MyWork() {
  const { me } = useAuth();
  const e = me?.employee;
  const count = (key: string, params: Record<string, string>) =>
    useQuery({ queryKey: ["tasks", "count", key], queryFn: () => api<TaskPage>("/tasks", { params: { mine: "true", page_size: 1, ...params } }) });
  const all = count("all", {});
  const done = count("done", { status: "completed" });
  const open = count("open", { open: "true" });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api<unknown[]>("/projects") });
  if (!e) return null;
  const stat = (label: string, value: number | undefined) => (
    <div className="rounded-lg bg-slate-50 px-3 py-2 text-center"><div className="text-xl font-semibold text-brand-ink">{value ?? "–"}</div><div className="text-xs text-slate-500">{label}</div></div>
  );
  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">My work</h2>
        <span className="text-xs text-slate-500">ID {e.employee_code}{e.department ? ` · ${e.department}` : ""}</span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stat("Tasks assigned", all.data?.total)}{stat("Not completed", open.data?.total)}{stat("Completed", done.data?.total)}{stat("Projects", projects.data?.length)}
      </div>
      <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-slate-500">My head</dt><dd className="font-medium">{e.head?.full_name ?? "No head (CEO / Owner review)"}</dd></div>
        <div><dt className="text-xs text-slate-500">Reports to</dt><dd className="font-medium">{e.reports_to?.full_name ?? "–"}</dd></div>
        <div><dt className="text-xs text-slate-500">QA tester</dt><dd className="font-medium">{e.qa?.full_name ?? "None"}</dd></div>
      </dl>
    </Card>
  );
}

function MyDay() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { me } = useAuth();
  const tz = me?.user.timezone;
  const open = useQuery({ queryKey: ["tasks", "mine", "open"], queryFn: () => api<TaskPage>("/tasks", { params: { mine: "true", open: "true", page_size: 50 } }), refetchInterval: 6000 });
  const load = useQuery({ queryKey: ["workload", "me"], queryFn: () => api<Workload | null>("/me/workload") });
  const startWork = useMutation({ mutationFn: (id: number) => api(`/tasks/${id}/start`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }) });
  const items = open.data?.items ?? [];
  const needExplanation = items.filter((t) => t.explanation_required);
  const next = items.slice(0, 5);
  const fresh = items.filter((t) => t.status === "assigned" || t.status === "reopened");
  const soon = items.filter((t) => !t.is_overdue && new Date(t.due_at).getTime() - Date.now() < 7 * 86_400_000);
  const w = load.data;

  return (
    <>
      <MyWork />
      {needExplanation.length > 0 && (
        <Card className="border-red-300 bg-red-50 p-4">
          <h2 className="text-sm font-semibold text-red-800">{needExplanation.length === 1 ? "A task is past its deadline" : `${needExplanation.length} tasks are past their deadline`}. Please explain the delay.</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {needExplanation.map((t) => <li key={t.id} className="flex flex-wrap items-center gap-3"><span className="font-medium">{t.title}</span><span className="text-xs text-red-700">due {fmtDay(t.due_at, tz)}</span><Button className="ml-auto py-1" variant="danger" onClick={() => nav(`/tasks/${t.id}`)}>Explain</Button></li>)}
          </ul>
        </Card>
      )}
      {w && (
        <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 p-4 text-sm">
          <span className="font-semibold">Your workload</span><LevelBadge level={w.level} />
          <span>{w.open_tasks} open · {w.overdue_tasks} overdue</span>
        </Card>
      )}
      {fresh.length > 0 && (
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold">New for you</h2>
          <ul className="divide-y divide-slate-100 text-sm">
            {fresh.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-3 py-2">
                <Link to={`/tasks/${t.id}`} className="font-medium hover:underline">{t.title}</Link>
                <span className="text-xs text-slate-500">from {t.assigned_by.full_name} · due {fmtDay(t.due_at, tz)}</span>
                <PriorityChip priority={t.priority} />
                <span className="ml-auto flex gap-2">
                  {t.status === "assigned" && <Button className="py-1" onClick={() => startWork.mutate(t.id)}>Start work</Button>}
                  <Button variant={t.status === "assigned" ? "outline" : "primary"} className="py-1" onClick={() => nav(`/tasks/${t.id}`)}>Open</Button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card className="p-5">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">Do this next</h2><Link to="/tasks" className="text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline">All my tasks</Link></div>
        {open.isLoading ? <p className="text-sm text-slate-500">Loading…</p> : next.length === 0 ? (
          <p className="text-sm text-slate-500">You have no open tasks. Nice work.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {next.map((t) => (
              <li key={t.id} onClick={() => nav(`/tasks/${t.id}`)} className="flex cursor-pointer flex-wrap items-center gap-3 py-2 hover:bg-slate-50">
                <span className="min-w-0 flex-1 truncate font-medium">{t.title} <span className="text-xs font-normal text-slate-400">{t.task_no}</span></span>
                <PriorityChip priority={t.priority} /><StatusBadge status={t.status} />{t.is_overdue && <OverdueBadge />}
                <span className="whitespace-nowrap text-xs text-slate-500">{fmtDay(t.due_at, tz)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {soon.length > 0 && (
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold">Deadlines in the next 7 days</h2>
          <ul className="space-y-1.5 text-sm">{soon.slice(0, 6).map((t) => <li key={t.id} className="flex justify-between gap-3"><Link to={`/tasks/${t.id}`} className="truncate hover:underline">{t.title}</Link><span className="whitespace-nowrap text-xs text-slate-500">{fmtDay(t.due_at, tz)}</span></li>)}</ul>
        </Card>
      )}
    </>
  );
}
