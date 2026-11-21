import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  BellRing,
  Building2,
  CheckCircle2,
  MailCheck,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  UserCheck,
  UserPlus,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card, PageHeader, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/components/task-ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Employee = {
  id: number;
  user_id: number;
  employee_code: string;
  full_name: string;
  email: string;
  job_title: string | null;
  department_id: number;
  status: string;
  is_active: boolean;
  roles: string[];
};

type Dept = {
  id: number;
  name: string;
  code: string;
  head_employee_id: number | null;
  is_active: boolean;
  is_system: boolean;
  self_service: boolean;
};

type RoleInvite = {
  id: number;
  email: string;
  role_code: string;
  role_name: string;
  claimed: boolean;
  claimed_at: string | null;
  created_at: string;
};

type JobStatus = {
  scheduler: { last_tick_at: string; scanned: boolean } | null;
  scheduler_running: boolean;
  email_backend: string;
  smtp_configured: boolean;
  app_base_url: string;
  email_links_are_local: boolean;
  pending_events: number;
  queued_emails: number;
  failed_emails: number;
  failed_events: number;
};

type AuditRow = {
  id: number;
  actor_user_id: number | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: unknown;
  after: unknown;
  ip: string | null;
  created_at: string;
};

export function AdminDashboard({ name }: { name?: string }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [passDone, setPassDone] = useState(false);
  const [resentId, setResentId] = useState<number | null>(null);

  const emps = useQuery({
    queryKey: ["admin", "employees-summary"],
    queryFn: () => api<{ items: Employee[]; total: number }>("/employees", { params: { page_size: 200 } }),
  });

  const depts = useQuery({
    queryKey: ["admin", "departments-summary"],
    queryFn: () => api<Dept[]>("/departments"),
  });

  const invites = useQuery({
    queryKey: ["admin", "role-invites-summary"],
    queryFn: () => api<RoleInvite[]>("/role-invites"),
  });

  const jobs = useQuery({
    queryKey: ["admin", "jobs-status"],
    queryFn: () => api<JobStatus>("/admin/jobs/status"),
  });

  const audit = useQuery({
    queryKey: ["admin", "recent-audit"],
    queryFn: () => api<{ items: AuditRow[]; total: number }>("/admin/audit-logs", { params: { page: 1, page_size: 6 } }),
  });

  const runPass = useMutation({
    mutationFn: () => api("/admin/jobs/run-now", { method: "POST" }),
    onSuccess: () => {
      setPassDone(true);
      setTimeout(() => setPassDone(false), 3000);
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  const resendInvite = useMutation({
    mutationFn: (id: number) => api(`/role-invites/${id}/resend`, { method: "POST" }),
    onSuccess: (_r, id) => {
      setResentId(id);
      setTimeout(() => setResentId(null), 3000);
      qc.invalidateQueries({ queryKey: ["admin", "role-invites-summary"] });
    },
  });

  const isLoading = emps.isLoading || depts.isLoading || invites.isLoading || jobs.isLoading;
  if (isLoading) return <Spinner />;

  const empList = emps.data?.items ?? [];
  const totalEmps = emps.data?.total ?? 0;
  const activeEmps = empList.filter((e) => e.is_active && e.status === "active").length;
  const pendingOnboarding = empList.filter((e) => e.status === "pending_setup").length;

  const deptList = (depts.data ?? []).filter((d) => !d.is_system);
  const activeDepts = deptList.filter((d) => d.is_active);
  const deptsWithHead = activeDepts.filter((d) => d.head_employee_id !== null).length;
  const deptsWithoutHead = activeDepts.filter((d) => d.head_employee_id === null);

  const inviteList = invites.data ?? [];
  const unclaimedInvites = inviteList.filter((i) => !i.claimed);
  const claimedInvites = inviteList.filter((i) => i.claimed);

  const js = jobs.data;
  const actorNames = new Map(empList.map((e) => [e.user_id, e.full_name]));
  const hasOwner = empList.some((e) => e.roles.some((r) => r.toLowerCase() === "owner")) || inviteList.some((i) => i.role_code === "owner");
  const hasCEO = empList.some((e) => e.roles.some((r) => r.toLowerCase() === "ceo")) || inviteList.some((i) => i.role_code === "ceo");

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome, ${name?.split(" ")[0] || "Administrator"}`}
        subtitle="System health, organization overview, and administration controls."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              disabled={runPass.isPending}
              onClick={() => runPass.mutate()}
              className="flex items-center gap-2"
            >
              <RefreshCw size={14} className={runPass.isPending ? "animate-spin" : ""} />
              {runPass.isPending ? "Running pass…" : passDone ? "Pass completed ✓" : "Run background pass"}
            </Button>
            <Button onClick={() => nav("/employees")}>
              <UserPlus size={14} className="mr-1.5" />
              Add employee
            </Button>
          </div>
        }
      />

      {/* 4 Primary KPI Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Link to="/employees" className="block group">
          <Card className="p-4 transition-all hover:border-indigo-300 hover:shadow-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Employees</span>
              <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600 group-hover:bg-indigo-100">
                <Users size={16} />
              </div>
            </div>
            <div className="mt-2 text-2xl font-bold text-slate-900">{totalEmps}</div>
            <p className="mt-1 text-xs text-slate-500">
              {activeEmps} active · {pendingOnboarding} pending onboarding
            </p>
          </Card>
        </Link>

        <Link to="/departments" className="block group">
          <Card className="p-4 transition-all hover:border-emerald-300 hover:shadow-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Departments</span>
              <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600 group-hover:bg-emerald-100">
                <Building2 size={16} />
              </div>
            </div>
            <div className="mt-2 text-2xl font-bold text-slate-900">{activeDepts.length}</div>
            <p className="mt-1 text-xs text-slate-500">
              {deptsWithHead} with Head · {deptsWithoutHead.length} without Head
            </p>
          </Card>
        </Link>

        <Link to="/role-emails" className="block group">
          <Card className="p-4 transition-all hover:border-blue-300 hover:shadow-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Role Invitations</span>
              <div className="rounded-lg bg-blue-50 p-2 text-blue-600 group-hover:bg-blue-100">
                <MailCheck size={16} />
              </div>
            </div>
            <div className="mt-2 text-2xl font-bold text-slate-900">{inviteList.length}</div>
            <p className="mt-1 text-xs text-slate-500">
              {unclaimedInvites.length} waiting for sign-up · {claimedInvites.length} claimed
            </p>
          </Card>
        </Link>

        <Link to="/admin/notifications" className="block group">
          <Card className="p-4 transition-all hover:border-purple-300 hover:shadow-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">Email Delivery</span>
              <div className="rounded-lg bg-purple-50 p-2 text-purple-600 group-hover:bg-purple-100">
                <BellRing size={16} />
              </div>
            </div>
            <div className="mt-2 text-2xl font-bold text-slate-900">{js?.queued_emails ?? 0} queued</div>
            <p className="mt-1 text-xs text-slate-500">
              {js?.failed_emails ?? 0} failed · {js?.pending_events ?? 0} pending events
            </p>
          </Card>
        </Link>
      </div>

      {/* Quick Action Navigation Buttons */}
      <Card className="p-4">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Administration Quick Actions</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Link
            to="/employees"
            className="flex flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-center transition-colors hover:border-indigo-200 hover:bg-indigo-50/50"
          >
            <Users size={18} className="text-indigo-600" />
            <span className="mt-2 text-xs font-medium text-slate-700">Employees</span>
          </Link>
          <Link
            to="/role-emails"
            className="flex flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-center transition-colors hover:border-blue-200 hover:bg-blue-50/50"
          >
            <MailCheck size={18} className="text-blue-600" />
            <span className="mt-2 text-xs font-medium text-slate-700">Role Emails</span>
          </Link>
          <Link
            to="/departments"
            className="flex flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-center transition-colors hover:border-emerald-200 hover:bg-emerald-50/50"
          >
            <Building2 size={18} className="text-emerald-600" />
            <span className="mt-2 text-xs font-medium text-slate-700">Departments</span>
          </Link>
          <Link
            to="/roles"
            className="flex flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-center transition-colors hover:border-violet-200 hover:bg-violet-50/50"
          >
            <ShieldCheck size={18} className="text-violet-600" />
            <span className="mt-2 text-xs font-medium text-slate-700">Roles & Perms</span>
          </Link>
          <Link
            to="/audit"
            className="flex flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-center transition-colors hover:border-rose-200 hover:bg-rose-50/50"
          >
            <ScrollText size={18} className="text-rose-600" />
            <span className="mt-2 text-xs font-medium text-slate-700">Audit Log</span>
          </Link>
        </div>
      </Card>

      {/* Two Column Layout: Setup & Invites vs Recent Activity */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left Column: Organization Setup & Pending Invites */}
        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="text-sm font-semibold text-slate-900">Organization Setup & Health</h2>
            <p className="mt-0.5 text-xs text-slate-500">Key milestones for configuring the organization.</p>
            <div className="mt-4 space-y-3">
              <div className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
                {hasOwner ? (
                  <CheckCircle2 size={18} className="shrink-0 text-emerald-600 mt-0.5" />
                ) : (
                  <AlertCircle size={18} className="shrink-0 text-amber-500 mt-0.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-800">Owner Account</span>
                    {hasOwner ? <Badge tone="green">Ready</Badge> : <Badge tone="orange">Needed</Badge>}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {hasOwner
                      ? "Owner role is registered or active. The Owner has top-level task and workload authority."
                      : "No Owner registered yet. Register an Owner email under Role emails."}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
                {hasCEO ? (
                  <CheckCircle2 size={18} className="shrink-0 text-emerald-600 mt-0.5" />
                ) : (
                  <AlertCircle size={18} className="shrink-0 text-slate-400 mt-0.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-800">CEO Account</span>
                    {hasCEO ? <Badge tone="green">Ready</Badge> : <Badge tone="grey">Optional</Badge>}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {hasCEO
                      ? "CEO role is registered or active with executive visibility."
                      : "Register the CEO's email under Role emails to give them senior leadership access."}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
                {deptsWithoutHead.length === 0 && activeDepts.length > 0 ? (
                  <CheckCircle2 size={18} className="shrink-0 text-emerald-600 mt-0.5" />
                ) : (
                  <AlertCircle size={18} className="shrink-0 text-amber-500 mt-0.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-800">Department Leadership</span>
                    {deptsWithoutHead.length === 0 && activeDepts.length > 0 ? (
                      <Badge tone="green">All Heads Named</Badge>
                    ) : (
                      <Badge tone="orange">{deptsWithoutHead.length} Missing Head</Badge>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {deptsWithoutHead.length === 0 && activeDepts.length > 0
                      ? "All active departments have a Department Head appointed."
                      : deptsWithoutHead.length > 0
                      ? `Departments without a Head: ${deptsWithoutHead.map((d) => d.name).join(", ")}. Tasks without a Head fall back to the Manager.`
                      : "No departments created yet. Add departments to organize employees."}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
                {js?.email_backend === "smtp" && js.smtp_configured ? (
                  <CheckCircle2 size={18} className="shrink-0 text-emerald-600 mt-0.5" />
                ) : (
                  <AlertCircle size={18} className="shrink-0 text-amber-500 mt-0.5" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-800">Email System</span>
                    {js?.email_backend === "smtp" ? <Badge tone="green">SMTP Active</Badge> : <Badge tone="orange">Log Mode</Badge>}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {js?.email_backend === "smtp"
                      ? "Real email delivery is operational. Notifications and invitations are sent through SMTP."
                      : "Email is currently writing to logs only. Configure SMTP in backend/.env to send real emails."}
                  </p>
                </div>
              </div>
            </div>
          </Card>

          {/* Pending Role Invitations Card */}
          <Card className="overflow-hidden p-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Role Invitations</h2>
                <p className="text-xs text-slate-500">Registered role emails awaiting sign-up.</p>
              </div>
              <Link to="/role-emails" className="text-xs font-medium text-indigo-600 hover:underline">
                View all ({inviteList.length}) →
              </Link>
            </div>

            {unclaimedInvites.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 p-4 text-center text-xs text-slate-500">
                <UserCheck size={18} className="mx-auto mb-1 text-slate-400" />
                All registered role emails have signed up.
              </div>
            ) : (
              <ul className="divide-y divide-slate-100 text-xs">
                {unclaimedInvites.slice(0, 4).map((i) => (
                  <li key={i.id} className="flex items-center justify-between py-2.5">
                    <div>
                      <div className="font-medium text-slate-800">{i.email}</div>
                      <div className="mt-0.5 flex items-center gap-2 text-slate-500">
                        <Badge tone="indigo">{i.role_name}</Badge>
                        <span>· Invited {fmtDateTime(i.created_at, me?.user.timezone)}</span>
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      className="py-1 text-xs"
                      disabled={resendInvite.isPending}
                      onClick={() => resendInvite.mutate(i.id)}
                    >
                      {resentId === i.id ? "Sent ✓" : "Resend"}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {/* Right Column: Recent Audit Log Activity */}
        <div className="space-y-6">
          <Card className="overflow-hidden p-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Recent Administrative Activity</h2>
                <p className="text-xs text-slate-500">Immutable audit log of organization modifications.</p>
              </div>
              <Link to="/audit" className="text-xs font-medium text-indigo-600 hover:underline">
                View all ({audit.data?.total ?? 0}) →
              </Link>
            </div>

            {audit.isLoading ? (
              <Spinner />
            ) : !audit.data?.items.length ? (
              <p className="text-xs text-slate-500">No audit activity logged yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table data-no-stack className="w-full text-left text-xs">
                  <thead className="border-b border-slate-100 text-slate-400">
                    <tr>
                      <th className="pb-2 font-medium">When</th>
                      <th className="pb-2 font-medium">Action</th>
                      <th className="pb-2 font-medium">Target</th>
                      <th className="pb-2 font-medium text-right">Actor</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {audit.data.items.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-50/60">
                        <td className="whitespace-nowrap py-2.5 text-slate-500">
                          {fmtDateTime(r.created_at, me?.user.timezone)}
                        </td>
                        <td className="py-2.5 font-medium text-slate-800">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-mono text-slate-700">
                            {r.action}
                          </span>
                        </td>
                        <td className="py-2.5 text-slate-600">
                          {r.entity_type} #{r.entity_id}
                        </td>
                        <td className="py-2.5 text-right text-slate-500">
                          {r.actor_user_id ? (actorNames.get(r.actor_user_id) ?? `User #${r.actor_user_id}`) : "System"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-3 border-t border-slate-100 pt-3 text-right">
              <Link to="/audit" className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline">
                Go to full audit log <ArrowRight size={12} />
              </Link>
            </div>
          </Card>

          {/* Pending Setup Employees (if any) */}
          {pendingOnboarding > 0 && (
            <Card className="border-amber-200 bg-amber-50/60 p-4">
              <div className="flex items-start gap-2.5">
                <AlertCircle size={16} className="mt-0.5 text-amber-700 shrink-0" />
                <div className="text-xs text-amber-900">
                  <div className="font-semibold">{pendingOnboarding} new sign-up(s) waiting to finish profile</div>
                  <p className="mt-0.5 text-amber-800">
                    These employees have signed up and are currently selecting their department and designation.
                  </p>
                  <Link to="/employees" className="mt-2 inline-block font-semibold text-amber-900 underline">
                    View in Employees →
                  </Link>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
