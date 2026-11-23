import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailCheck, Network, UserPlus } from "lucide-react";
import { useState, useMemo, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { Can, useAuth } from "@/lib/auth";

type Employee = {
  id: number; employee_code: string; full_name: string; email: string; job_title: string | null;
  department_id: number; company_id?: number; status: string; is_active: boolean; roles: string[]; reports_to_id: number | null;
};
type Dept = { id: number; name: string; code: string; company_id?: number; is_active: boolean };
type Company = { id: number; name: string; code: string };
type Page = { items: Employee[]; total: number };

export function Employees() {
  const qc = useQueryClient();
  const { can, me } = useAuth();
  const isOwner = Boolean(me?.roles?.includes("owner"));
  const isCeo = Boolean(me?.roles?.includes("ceo") && !isOwner && !me?.roles?.includes("admin"));

  const [params] = useSearchParams();
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [creating, setCreating] = useState(params.get("add") === "1");
  const [editing, setEditing] = useState<Employee | null>(null);

  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<Company[]>("/companies") });
  const depts = useQuery({ queryKey: ["departments"], queryFn: () => api<Dept[]>("/departments") });
  const list = useQuery({
    queryKey: ["employees", q, dept, companyId],
    queryFn: () => api<Page>("/employees", { params: { q, department_id: dept, company_id: companyId || undefined, page_size: 100 } }),
  });
  const deptName = (id: number) => depts.data?.find((d) => d.id === id)?.name ?? "—";
  const byId = new Map(list.data?.items.map((e) => [e.id, e.full_name]));

  const deactivate = useMutation({
    mutationFn: (id: number) => api(`/employees/${id}/deactivate`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["employees"] }),
  });

  return (
    <>
      <PageHeader
        title="Employees & Staff Directory"
        subtitle={`${list.data?.total ?? 0} people in your scope`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to="/role-emails"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
            >
              <MailCheck size={15} /> Invite by Email
            </Link>
            {can("hierarchy.manage") && (
              <Link
                to="/hierarchy"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
              >
                <Network size={15} /> View Hierarchy
              </Link>
            )}
            <Can permission="employee.manage">
              <Button onClick={() => setCreating((v) => !v)} className="bg-indigo-600 hover:bg-indigo-700 text-white">
                <UserPlus size={15} /> {creating ? "Close Form" : "Add Employee Directly"}
              </Button>
            </Can>
          </div>
        }
      />
      {creating && (
        <CreateEmployee
          depts={depts.data ?? []}
          employees={list.data?.items ?? []}
          companies={companies.data ?? []}
          isCeo={isCeo}
          onDone={() => { setCreating(false); qc.invalidateQueries({ queryKey: ["employees"] }); qc.invalidateQueries({ queryKey: ["hierarchy-tree"] }); }}
        />
      )}
      {editing && (
        <EditEmployee
          key={editing.id}
          emp={editing}
          depts={depts.data ?? []}
          employees={list.data?.items ?? []}
          isCeo={isCeo}
          onClose={() => setEditing(null)}
          onDone={() => { setEditing(null); qc.invalidateQueries({ queryKey: ["employees"] }); qc.invalidateQueries({ queryKey: ["hierarchy-tree"] }); }}
        />
      )}
      <div className="mb-4 flex flex-wrap gap-3">
        <Input className="max-w-xs" placeholder="Search name or code" value={q} onChange={(e) => setQ(e.target.value)} />
        {companies.data && companies.data.length > 1 && (
          <Select className="max-w-xs" value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
            <option value="">All companies</option>
            {companies.data.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code.toUpperCase()})</option>)}
          </Select>
        )}
        <Select className="max-w-xs" value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">All departments</option>
          {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </div>
      <Card className="overflow-x-auto">
        {list.isLoading ? <Spinner /> : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="p-3">Name</th><th className="p-3">Department</th><th className="p-3">Roles</th><th className="p-3">Reports to</th><th className="p-3">Status</th><th className="p-3" /></tr>
            </thead>
            <tbody>
              {list.data?.items.map((e) => (
                <tr key={e.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/80 transition-colors">
                  <td className="p-3"><div className="font-medium text-slate-900">{e.full_name}</div><div className="text-xs text-slate-500">{e.employee_code} · {e.job_title ?? e.email}</div></td>
                  <td className="p-3 text-slate-700">{deptName(e.department_id)}</td>
                  <td className="p-3"><div className="flex flex-wrap gap-1">{e.roles.map((r) => <Badge key={r} tone={r === "owner" ? "orange" : r === "ceo" ? "purple" : r === "manager" ? "indigo" : "grey"}>{r.replace("_", " ")}</Badge>)}</div></td>
                  <td className="p-3 text-slate-700">{e.reports_to_id ? byId.get(e.reports_to_id) ?? `#${e.reports_to_id}` : "—"}</td>
                  <td className="p-3"><Badge tone={e.is_active ? "green" : "grey"}>{e.is_active ? e.status.replace("_", " ") : "inactive"}</Badge></td>
                  <td className="p-3 text-right">
                    {can("employee.manage") && e.is_active && (
                      <Button variant="ghost" onClick={() => setEditing(e)}>Edit</Button>
                    )}
                    {can("employee.manage") && e.is_active && (
                      <Button variant="ghost" className="text-red-600 hover:text-red-700" onClick={() => confirm(`Deactivate ${e.full_name}? They will be signed out immediately.`) && deactivate.mutate(e.id)}>Deactivate</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <ErrorNote error={list.error ?? deactivate.error} />
    </>
  );
}

const ALL_ROLES = ["employee", "sub_head", "department_head", "manager", "ceo", "owner"];

function EditEmployee({ emp, depts, employees, isCeo, onClose, onDone }: { emp: Employee; depts: Dept[]; employees: Employee[]; isCeo: boolean; onClose: () => void; onDone: () => void }) {
  const allowedRoles = useMemo(() => {
    if (isCeo) return ["employee", "sub_head", "department_head", "manager"];
    return ALL_ROLES;
  }, [isCeo]);

  const [f, setF] = useState({
    job_title: emp.job_title ?? "",
    department_id: String(emp.department_id),
    role: emp.roles[0] ?? "employee",
    reports_to_id: emp.reports_to_id ? String(emp.reports_to_id) : "",
    status: emp.status === "on_leave" ? "on_leave" : "active",
  });
  const m = useMutation({
    mutationFn: async () => {
      const patch: Record<string, unknown> = { job_title: f.job_title || null, department_id: Number(f.department_id), status: f.status };
      // Only send roles when changed: a role change signs that user out so new permissions apply at once.
      if (f.role !== (emp.roles[0] ?? "employee")) patch.role_codes = [f.role];
      await api(`/employees/${emp.id}`, { method: "PATCH", body: patch });
      const newBoss = f.reports_to_id ? Number(f.reports_to_id) : null;
      if (newBoss !== emp.reports_to_id) await api("/hierarchy/relationships", { body: { employee_id: emp.id, reports_to_id: newBoss } });
    },
    onSuccess: onDone,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Card className="mb-5 p-5">
      <h2 className="mb-4 text-sm font-semibold text-slate-900">Edit {emp.full_name} <span className="font-normal text-slate-500">· {emp.employee_code}</span></h2>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Job title"><Input value={f.job_title} onChange={set("job_title")} /></Field>
        <Field label="Department">
          <Select value={f.department_id} onChange={set("department_id")}>
            {depts.filter((d) => d.is_active || String(d.id) === f.department_id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
        <Field label="Role">
          <Select value={f.role} onChange={set("role")}>
            {[...new Set([...allowedRoles, f.role])].map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
          </Select>
        </Field>
        <Field label="Reports to">
          <Select value={f.reports_to_id} onChange={set("reports_to_id")}>
            <option value="">None (Top Level / Executive)</option>
            {employees.filter((e) => e.id !== emp.id).map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
          </Select>
        </Field>
        <Field label="Availability">
          <Select value={f.status} onChange={set("status")}>
            <option value="active">Active</option>
            <option value="on_leave">On leave</option>
          </Select>
        </Field>
        <div className="flex items-end gap-2">
          <Button type="submit" disabled={m.isPending} className="bg-indigo-600 hover:bg-indigo-700 text-white">Save changes</Button>
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        </div>
        <div className="sm:col-span-2 lg:col-span-3"><ErrorNote error={m.error} /></div>
      </form>
    </Card>
  );
}

export function CreateEmployee({ depts, employees, companies, isCeo, onDone }: { depts: Dept[]; employees: Employee[]; companies: Company[]; isCeo: boolean; onDone: () => void }) {
  const allowedRoles = useMemo(() => {
    if (isCeo) return ["employee", "sub_head", "department_head", "manager"];
    return ALL_ROLES;
  }, [isCeo]);

  const [f, setF] = useState({
    email: "", full_name: "", employee_code: "",
    company_id: companies.length > 0 ? String(companies[0].id) : "1",
    department_id: "", job_title: "", temp_password: "", role: "employee", reports_to_id: ""
  });

  // Filter departments for chosen company
  const availableDepts = useMemo(() => {
    const cid = Number(f.company_id);
    return depts.filter((d) => d.is_active && (!d.company_id || d.company_id === cid));
  }, [depts, f.company_id]);

  const m = useMutation({
    mutationFn: () =>
      api("/employees", {
        body: {
          email: f.email, full_name: f.full_name, employee_code: f.employee_code.trim() || undefined,
          department_id: Number(f.department_id),
          company_id: Number(f.company_id) || undefined,
          job_title: f.job_title || null, temp_password: f.temp_password, role_codes: [f.role],
          reports_to_id: f.reports_to_id ? Number(f.reports_to_id) : null,
        },
      }),
    onSuccess: onDone,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Card className="mb-5 p-5 border-indigo-200 bg-indigo-50/20 shadow-sm">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-indigo-950">Add Employee Directly</h2>
        <p className="text-xs text-slate-500">Create an employee account immediately and assign their department, role, and reporting manager.</p>
      </div>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Full name"><Input required value={f.full_name} onChange={set("full_name")} placeholder="e.g. Alex Morgan" /></Field>
        <Field label="Email address"><Input type="email" required value={f.email} onChange={set("email")} placeholder="alex@company.com" /></Field>
        {companies.length > 0 && (
          <Field label="Company">
            <Select value={f.company_id} onChange={set("company_id")}>
              {companies.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code.toUpperCase()})</option>)}
            </Select>
          </Field>
        )}
        <Field label="Department">
          <Select required value={f.department_id} onChange={set("department_id")}>
            <option value="">Select department…</option>
            {availableDepts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
        <Field label="Job title"><Input value={f.job_title} onChange={set("job_title")} placeholder="e.g. Senior Backend Engineer" /></Field>
        <Field label="Role to Assign">
          <Select value={f.role} onChange={set("role")}>
            {allowedRoles.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
          </Select>
        </Field>
        <Field label="Reports to (Manager)">
          <Select value={f.reports_to_id} onChange={set("reports_to_id")}>
            <option value="">None (Top Level / Executive)</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
          </Select>
        </Field>
        <Field label="Employee ID / Code (optional)"><Input value={f.employee_code} onChange={set("employee_code")} placeholder="Leave blank for auto-generation" /></Field>
        <Field label="Temporary password (must change at first login)"><Input type="password" required minLength={10} value={f.temp_password} onChange={set("temp_password")} placeholder="At least 10 chars" /></Field>
        <div className="flex items-end gap-2">
          <Button type="submit" disabled={m.isPending} className="bg-indigo-600 hover:bg-indigo-700 text-white">Create Employee</Button>
        </div>
        <div className="sm:col-span-2 lg:col-span-3"><ErrorNote error={m.error} /></div>
      </form>
    </Card>
  );
}
