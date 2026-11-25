import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Building2, FolderPlus, Network, PlusCircle, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, Card, PageHeader, Select } from "@/components/ui";
import { fmtDay, LevelBadge, OverdueBadge, PriorityChip, StatusBadge, type DelayQueue, type TaskPage, type Workload } from "@/components/task-ui";
import { OverviewPanel } from "@/components/Overview";
import { AdminDashboard } from "@/components/AdminDashboard";
import { OrgHierarchyTree } from "@/components/OrgHierarchyTree";
import { PendingApprovalsCard } from "@/components/PendingApprovalsCard";
import { CreateEmployee } from "@/pages/Employees";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Company = { id: number; name: string; code: string };
type Dept = { id: number; name: string; code: string; company_id?: number; is_active: boolean };

/** Employee-first "My Day". People who assign work also get a short "needs your attention" list. */
export function Dashboard() {
  const { me, can } = useAuth();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const name = me?.employee?.full_name ?? me?.user.email;
  const isOwner = Boolean(me?.roles?.includes("owner"));
  const isCEO = Boolean(me?.roles?.includes("ceo"));
  const isAdmin = Boolean(me?.roles?.includes("admin"));
  const isLeadership = isOwner || isCEO;

  const [showAddEmployee, setShowAddEmployee] = useState(false);
  const [hierCompanyId, setHierCompanyId] = useState("");

  const companiesQ = useQuery({ queryKey: ["companies"], queryFn: () => api<Company[]>("/companies"), enabled: isLeadership });
  const deptsQ = useQuery({ queryKey: ["departments"], queryFn: () => api<Dept[]>("/departments"), enabled: isLeadership });
  const empsQ = useQuery({
    queryKey: ["employees", "leadership-summary"],
    queryFn: () => api<{ items: any[]; total: number }>("/employees", { params: { page_size: 200 } }),
    enabled: isLeadership,
  });

  const effectiveHierCompanyId = useMemo(() => {
    if (hierCompanyId) return hierCompanyId;
    if (companiesQ.data && companiesQ.data.length > 0) return String(companiesQ.data[0].id);
    return "";
  }, [hierCompanyId, companiesQ.data]);

  const hierCidNum = effectiveHierCompanyId ? Number(effectiveHierCompanyId) : undefined;

  // Admin cannot access the Owner Panel and has no task authority, so Admin always sees AdminDashboard
  if ((isAdmin && !isOwner) || !can("task.view")) {
    return <AdminDashboard name={name} />;
  }

  const activePanel = params.get("panel") || "owner";

  if (isOwner && activePanel === "admin") {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
          <div className="inline-flex rounded-xl bg-slate-100 p-1 border border-slate-200/80 shadow-inner">
            <button
              type="button"
              onClick={() => setParams({ panel: "owner" })}
              className="flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors"
            >
              <span>👑</span> Owner Executive Panel
            </button>
            <button
              type="button"
              onClick={() => setParams({ panel: "admin" })}
              className="flex items-center gap-2 rounded-lg bg-white px-3.5 py-1.5 text-xs font-semibold text-indigo-700 shadow-sm"
            >
              <span>⚙️</span> Admin Panel
            </button>
          </div>
          <span className="text-xs font-medium text-slate-500">Highest authority: viewing System Administration</span>
        </div>
        <AdminDashboard name={name} />
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title={`Welcome, ${name?.split(" ")[0]}`}
          subtitle={
            isOwner
              ? "Owner Executive Overview & System Control"
              : isCEO
              ? "CEO Executive Overview & Company Management"
              : "Here is what needs you today."
          }
        />
        {isCEO && !isOwner && (
          <div className="inline-flex items-center gap-1.5 rounded-xl bg-purple-50 px-3.5 py-1.5 border border-purple-200 text-xs font-semibold text-purple-700 shadow-sm">
            <span>💼</span> CEO Executive Panel
          </div>
        )}
        {isOwner && (
          <div className="inline-flex rounded-xl bg-slate-100 p-1 border border-slate-200/80 shadow-inner">
            <button
              type="button"
              onClick={() => setParams({ panel: "owner" })}
              className="flex items-center gap-2 rounded-lg bg-white px-3.5 py-1.5 text-xs font-semibold text-indigo-700 shadow-sm"
            >
              <span>👑</span> Owner Executive Panel
            </button>
            <button
              type="button"
              onClick={() => setParams({ panel: "admin" })}
              className="flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors"
            >
              <span>⚙️</span> Admin Panel
            </button>
          </div>
        )}
      </div>
      <div className="space-y-5">
        {isLeadership && (
          <div className="space-y-4">
            <PendingApprovalsCard compact={true} />
            {/* Quick Action Navigation Buttons */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-gradient-to-r from-indigo-50/90 via-slate-50 to-blue-50/80 p-3.5 border border-indigo-100 shadow-sm">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold text-xs shadow-sm">⚡</span>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-indigo-700">Quick Actions</div>
                  <div className="text-xs text-slate-500">Fast action tabs for Owner & CEO panels</div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to="/tasks/new"
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors"
                >
                  <PlusCircle size={15} /> Assign Task
                </Link>
                <Link
                  to="/projects?new=1"
                  className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-xs font-semibold text-slate-800 border border-slate-300 shadow-sm hover:bg-slate-50 transition-colors"
                >
                  <FolderPlus size={15} /> Assign Project
                </Link>
                {can("employee.manage") && (
                  <Link
                    to="/employees?add=1"
                    className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-xs font-semibold text-slate-800 border border-slate-300 shadow-sm hover:bg-slate-50 transition-colors"
                  >
                    <UserPlus size={15} /> Add Employee
                  </Link>
                )}
                {can("employee.manage") && (
                  <Link
                    to="/role-emails"
                    className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-xs font-semibold text-slate-800 border border-slate-300 shadow-sm hover:bg-slate-50 transition-colors"
                  >
                    <span>✉️</span> Invite by Email
                  </Link>
                )}
                {can("hierarchy.manage") && (
                  <Link
                    to="/hierarchy"
                    className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-xs font-semibold text-slate-800 border border-slate-300 shadow-sm hover:bg-slate-50 transition-colors"
                  >
                    <Network size={15} /> Manage Hierarchy
                  </Link>
                )}
                {can("department.manage") && (
                  <Link
                    to="/departments"
                    className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-xs font-semibold text-slate-800 border border-slate-300 shadow-sm hover:bg-slate-50 transition-colors"
                  >
                    <Building2 size={15} /> Departments & Heads
                  </Link>
                )}
              </div>
            </div>
          </div>
        )}

        <ReviewWaiting />
        {can("task.assign") && <Attention />}
        {me?.permissions["task.view"] !== "self" && <OverviewPanel />}
        <MyDay />

        {/* Executive Management Section: Hub Cards & Live Hierarchy at end of Dashboard */}
        {isLeadership && (
          <div className="space-y-5 pt-6 border-t border-slate-200/90">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                {isOwner ? "Owner Operations & Organization Structure" : "CEO Operations & Organization Structure"}
              </span>
              <div className="h-px flex-1 bg-slate-200" />
            </div>

            {/* Executive Operations Hub Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {/* Card 1: Employees & Roles */}
              <Card className="p-4 transition-all hover:border-indigo-300 hover:shadow-md bg-white border border-slate-200/80">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Staffing</span>
                  <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600">
                    <Users size={18} />
                  </div>
                </div>
                <div className="mt-2 text-base font-bold text-slate-900">Employees & Roles</div>
                <p className="mt-1 text-xs text-slate-500">
                  Add team members, assign management or staff roles, and send invitations.
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
                  {can("employee.manage") && (
                    <Link
                      to="/employees?add=1"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
                    >
                      <UserPlus size={13} /> Add
                    </Link>
                  )}
                  {can("employee.manage") && (
                    <Link
                      to="/role-emails"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-slate-800"
                    >
                      ✉️ Invite
                    </Link>
                  )}
                  <Link
                    to="/employees"
                    className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700 ml-auto"
                  >
                    Directory →
                  </Link>
                </div>
              </Card>

              {/* Card 2: Org Hierarchy */}
              <Card className="p-4 transition-all hover:border-purple-300 hover:shadow-md bg-white border border-slate-200/80">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Structure</span>
                  <div className="rounded-lg bg-purple-50 p-2 text-purple-600">
                    <Network size={18} />
                  </div>
                </div>
                <div className="mt-2 text-base font-bold text-slate-900">Org Hierarchy</div>
                <p className="mt-1 text-xs text-slate-500">
                  Interactive org tree, direct manager reporting lines, and cycle-free management.
                </p>
                <div className="mt-4 flex flex-wrap gap-2 pt-2 border-t border-slate-100">
                  {can("hierarchy.manage") && (
                    <Link
                      to="/hierarchy"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-purple-600 hover:text-purple-800"
                    >
                      <Network size={13} /> Manage Hierarchy →
                    </Link>
                  )}
                </div>
              </Card>

              {/* Card 3: Departments & Leaders */}
              <Card className="p-4 transition-all hover:border-emerald-300 hover:shadow-md bg-white border border-slate-200/80">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Departments</span>
                  <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600">
                    <Building2 size={18} />
                  </div>
                </div>
                <div className="mt-2 text-base font-bold text-slate-900">Departments & Heads</div>
                <p className="mt-1 text-xs text-slate-500">
                  Create departments, name Department Heads and SubHeads, and set QA testers.
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
                  {can("department.manage") && (
                    <Link
                      to="/departments?add=1"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-800"
                    >
                      + Add Dept
                    </Link>
                  )}
                  {can("department.manage") && (
                    <Link
                      to="/departments"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-slate-800 ml-auto"
                    >
                      Set Heads →
                    </Link>
                  )}
                </div>
              </Card>

              {/* Card 4: Multi-Company Operations (Owner) or Company Profile (CEO) */}
              <Card className="p-4 transition-all hover:border-amber-300 hover:shadow-md bg-white border border-slate-200/80">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    {isOwner ? "Enterprise" : "Authorized Scope"}
                  </span>
                  <div className="rounded-lg bg-amber-50 p-2 text-amber-600">
                    <ShieldCheck size={18} />
                  </div>
                </div>
                <div className="mt-2 text-base font-bold text-slate-900">
                  {isOwner ? "Companies & CEOs" : "Company Scope"}
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {isOwner
                    ? "Add companies, appoint CEOs, and authorize company-specific management."
                    : "Manage your assigned company operations, team hierarchy, and AI memory."}
                </p>
                <div className="mt-4 flex flex-wrap gap-2 pt-2 border-t border-slate-100">
                  {can("employee.manage") && (
                    <Link
                      to="/companies"
                      className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 hover:text-amber-900"
                    >
                      {isOwner ? "Manage Companies & CEOs →" : "View Company Details →"}
                    </Link>
                  )}
                </div>
              </Card>
            </div>

            {/* Live Organization Hierarchy & Team Management Card */}
            <Card className="p-5 border-slate-200/90 bg-white shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 text-white shadow-sm">
                    <Network size={19} />
                  </span>
                  <div>
                    <h2 className="text-sm font-bold text-slate-900">
                      {isOwner ? "Organization Hierarchy & Team Management" : "Authorized Company Hierarchy & Team Management"}
                    </h2>
                    <p className="text-xs text-slate-500">
                      Hold and move any employee card to dynamically update reporting managers without reloading.
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {companiesQ.data && companiesQ.data.length > 1 && (
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold uppercase text-slate-500">Company:</span>
                      <Select
                        value={effectiveHierCompanyId}
                        onChange={(e) => setHierCompanyId(e.target.value)}
                        className="text-xs font-medium py-1 w-44"
                      >
                        {companiesQ.data.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name} ({c.code.toUpperCase()})
                          </option>
                        ))}
                      </Select>
                    </div>
                  )}

                  {can("employee.manage") && (
                    <Button
                      onClick={() => setShowAddEmployee((v) => !v)}
                      className="text-xs py-1.5 px-3 bg-indigo-600 hover:bg-indigo-700 text-white"
                    >
                      <UserPlus size={14} className="mr-1.5" />
                      {showAddEmployee ? "Close Form" : "Add Employee Directly"}
                    </Button>
                  )}

                  {can("employee.manage") && (
                    <Link
                      to="/role-emails"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
                    >
                      <span>✉️</span> Invite by Email
                    </Link>
                  )}

                  <Link
                    to="/hierarchy"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
                  >
                    <Network size={14} /> Full Hierarchy →
                  </Link>
                </div>
              </div>

              {/* Collapsible Inline Add Employee Form */}
              {showAddEmployee && (
                <div className="pt-1">
                  <CreateEmployee
                    depts={deptsQ.data ?? []}
                    employees={empsQ.data?.items ?? []}
                    companies={companiesQ.data ?? []}
                    isCeo={isCEO && !isOwner}
                    onDone={() => {
                      setShowAddEmployee(false);
                      qc.invalidateQueries({ queryKey: ["employees"] });
                      qc.invalidateQueries({ queryKey: ["hierarchy-tree"] });
                    }}
                  />
                </div>
              )}

              {/* Interactive Org Hierarchy Tree with Drag & Drop */}
              <OrgHierarchyTree
                companyId={hierCidNum}
                canManage={can("hierarchy.manage")}
                compact={true}
                showControls={true}
                onAddEmployeeClick={() => setShowAddEmployee(true)}
              />
            </Card>
          </div>
        )}
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
