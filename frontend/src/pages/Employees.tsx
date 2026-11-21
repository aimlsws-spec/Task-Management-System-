import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { Can, useAuth } from "@/lib/auth";

type Employee = {
  id: number; employee_code: string; full_name: string; email: string; job_title: string | null;
  department_id: number; status: string; is_active: boolean; roles: string[]; reports_to_id: number | null;
};
type Dept = { id: number; name: string; is_active: boolean };
type Page = { items: Employee[]; total: number };

export function Employees() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Employee | null>(null);

  const depts = useQuery({ queryKey: ["departments"], queryFn: () => api<Dept[]>("/departments") });
  const list = useQuery({
    queryKey: ["employees", q, dept],
    queryFn: () => api<Page>("/employees", { params: { q, department_id: dept, page_size: 100 } }),
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
        title="Employees"
        subtitle={`${list.data?.total ?? 0} people in your scope`}
        actions={<Can permission="employee.manage"><Button onClick={() => setCreating((v) => !v)}>{creating ? "Close" : "Add employee"}</Button></Can>}
      />
      {creating && <CreateEmployee depts={depts.data ?? []} employees={list.data?.items ?? []} onDone={() => { setCreating(false); qc.invalidateQueries({ queryKey: ["employees"] }); }} />}
      {editing && (
        <EditEmployee
          key={editing.id}
          emp={editing}
          depts={depts.data ?? []}
          employees={list.data?.items ?? []}
          onClose={() => setEditing(null)}
          onDone={() => { setEditing(null); qc.invalidateQueries({ queryKey: ["employees"] }); qc.invalidateQueries({ queryKey: ["hierarchy"] }); }}
        />
      )}
      <div className="mb-4 flex flex-wrap gap-3">
        <Input className="max-w-xs" placeholder="Search name or code" value={q} onChange={(e) => setQ(e.target.value)} />
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
                <tr key={e.id} className="border-b border-slate-100 last:border-0">
                  <td className="p-3"><div className="font-medium">{e.full_name}</div><div className="text-xs text-slate-500">{e.employee_code} · {e.job_title ?? e.email}</div></td>
                  <td className="p-3">{deptName(e.department_id)}</td>
                  <td className="p-3"><div className="flex flex-wrap gap-1">{e.roles.map((r) => <Badge key={r} tone="indigo">{r.replace("_", " ")}</Badge>)}</div></td>
                  <td className="p-3">{e.reports_to_id ? byId.get(e.reports_to_id) ?? `#${e.reports_to_id}` : "—"}</td>
                  <td className="p-3"><Badge tone={e.is_active ? "green" : "grey"}>{e.is_active ? e.status.replace("_", " ") : "inactive"}</Badge></td>
                  <td className="p-3 text-right">
                    {can("employee.manage") && e.is_active && (
                      <Button variant="ghost" onClick={() => setEditing(e)}>Edit</Button>
                    )}
                    {can("employee.manage") && e.is_active && (
                      <Button variant="ghost" onClick={() => confirm(`Deactivate ${e.full_name}? They will be signed out immediately.`) && deactivate.mutate(e.id)}>Deactivate</Button>
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

const ROLE_OPTIONS = ["employee", "department_head", "manager", "ceo", "owner", "admin"];

function EditEmployee({ emp, depts, employees, onClose, onDone }: { emp: Employee; depts: Dept[]; employees: Employee[]; onClose: () => void; onDone: () => void }) {
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
      <h2 className="mb-4 text-sm font-semibold">Edit {emp.full_name} <span className="font-normal text-slate-500">· {emp.employee_code}</span></h2>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Job title"><Input value={f.job_title} onChange={set("job_title")} /></Field>
        <Field label="Department">
          <Select value={f.department_id} onChange={set("department_id")}>
            {depts.filter((d) => d.is_active || String(d.id) === f.department_id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
        <Field label="Role">
          <Select value={f.role} onChange={set("role")}>
            {[...new Set([...ROLE_OPTIONS, f.role])].map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
          </Select>
        </Field>
        <Field label="Reports to">
          <Select value={f.reports_to_id} onChange={set("reports_to_id")}>
            <option value="">None</option>
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
          <Button type="submit" disabled={m.isPending}>Save changes</Button>
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        </div>
        <div className="sm:col-span-2 lg:col-span-3"><ErrorNote error={m.error} /></div>
      </form>
    </Card>
  );
}

function CreateEmployee({ depts, employees, onDone }: { depts: Dept[]; employees: Employee[]; onDone: () => void }) {
  const [f, setF] = useState({ email: "", full_name: "", employee_code: "", department_id: "", job_title: "", temp_password: "", role: "employee", reports_to_id: "" });
  const m = useMutation({
    mutationFn: () =>
      api("/employees", {
        body: {
          email: f.email, full_name: f.full_name, employee_code: f.employee_code.trim() || undefined, department_id: Number(f.department_id),
          job_title: f.job_title || null, temp_password: f.temp_password, role_codes: [f.role],
          reports_to_id: f.reports_to_id ? Number(f.reports_to_id) : null,
        },
      }),
    onSuccess: onDone,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Card className="mb-5 p-5">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Full name"><Input required value={f.full_name} onChange={set("full_name")} /></Field>
        <Field label="Email"><Input type="email" required value={f.email} onChange={set("email")} /></Field>
        <Field label="Employee ID (optional)"><Input value={f.employee_code} onChange={set("employee_code")} placeholder="Leave empty: a unique ID like SW-7K2QX9 is created" /></Field>
        <Field label="Department">
          <Select required value={f.department_id} onChange={set("department_id")}>
            <option value="">Select…</option>
            {depts.filter((d) => d.is_active).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
        <Field label="Job title"><Input value={f.job_title} onChange={set("job_title")} /></Field>
        <Field label="Role">
          <Select value={f.role} onChange={set("role")}>
            {["employee", "department_head", "manager", "ceo", "owner", "admin"].map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
          </Select>
        </Field>
        <Field label="Reports to">
          <Select value={f.reports_to_id} onChange={set("reports_to_id")}>
            <option value="">None</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
          </Select>
        </Field>
        <Field label="Temporary password (must be changed at first login)"><Input type="password" required minLength={10} value={f.temp_password} onChange={set("temp_password")} /></Field>
        <div className="flex items-end"><Button type="submit" disabled={m.isPending}>Create employee</Button></div>
        <div className="sm:col-span-2 lg:col-span-3"><ErrorNote error={m.error} /></div>
      </form>
    </Card>
  );
}
