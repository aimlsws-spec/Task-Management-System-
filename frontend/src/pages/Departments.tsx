import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Dept = {
  id: number;
  name: string;
  code: string;
  company_id?: number;
  head_employee_id: number | null;
  sub_head_employee_id: number | null;
  head_employee_ids?: number[];
  sub_head_employee_ids?: number[];
  qa_employee_id: number | null;
  is_active: boolean;
  is_system: boolean;
  self_service: boolean;
  is_shared?: boolean;
  company_ids?: number[];
};
type Emp = { id: number; full_name: string; is_active: boolean };

/** Administration > Departments: add, rename, activate/deactivate, delete, choose heads and QA testers, control sign-up visibility. */
export function Departments() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const depts = useQuery({ queryKey: ["departments"], queryFn: () => api<Dept[]>("/departments") });
  const emps = useQuery({ queryKey: ["employees", "all"], queryFn: () => api<{ items: Emp[] }>("/employees", { params: { page_size: 200 } }), enabled: can("employee.view") });
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [regroup, setRegroup] = useState(true);
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null);
  const [managingLeaders, setManagingLeaders] = useState<Dept | null>(null);
  const [notice, setNotice] = useState("");

  const refresh = () => { qc.invalidateQueries({ queryKey: ["departments"] }); qc.invalidateQueries({ queryKey: ["employees"] }); qc.invalidateQueries({ queryKey: ["hierarchy"] }); };
  const create = useMutation({ mutationFn: () => api("/departments", { body: { name, code } }), onSuccess: () => { setName(""); setCode(""); refresh(); } });
  const patch = useMutation({ mutationFn: (v: { id: number; body: Record<string, unknown> }) => api(`/departments/${v.id}`, { method: "PATCH", body: v.body }), onSuccess: () => { setEditing(null); refresh(); } });
  const del = useMutation({ mutationFn: (id: number) => api(`/departments/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const setHead = useMutation({
    mutationFn: (v: { id: number; head: number | null }) => api<{ members_moved: number }>(`/departments/${v.id}/head`, { method: "PUT", body: { head_employee_id: v.head, regroup_members: regroup } }),
    onSuccess: (r) => { setNotice(r.members_moved ? `${r.members_moved} member(s) moved under the new head.` : ""); refresh(); },
  });
  const setSubHead = useMutation({
    mutationFn: (v: { id: number; subhead: number | null }) => api(`/departments/${v.id}/subhead`, { method: "PUT", body: { sub_head_employee_id: v.subhead } }),
    onSuccess: () => { setNotice("Department SubHead updated."); refresh(); },
  });
  const setQa = useMutation({
    mutationFn: (v: { id: number; qa: number | null }) => api(`/departments/${v.id}/qa`, { method: "PUT", body: { qa_employee_id: v.qa } }),
    onSuccess: refresh,
  });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };
  const err = create.error ?? patch.error ?? del.error ?? setHead.error ?? setSubHead.error ?? setQa.error;

  return (
    <>
      <PageHeader title="Departments" subtitle="Choosing a head also gives that person the Department Head role (they sign in again to use it). Departments without a head are managed by the Manager. A department's QA tester tests its finished work first; its head reviews next; then the CEO or Owner." />
      <Card className="mb-5 p-5">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Field label="Name"><Input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Code"><Input required pattern="[A-Za-z0-9_-]+" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
          <Button type="submit" disabled={create.isPending}>Add department</Button>
        </form>
        <label className="mt-4 flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={regroup} onChange={(e) => setRegroup(e.target.checked)} />
          When I change a department head, move that department's members under the new head
        </label>
        {notice && <p className="mt-2 text-sm text-green-700">{notice}</p>}
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Card>

      <Card className="overflow-x-auto">
        {depts.isLoading ? <Spinner /> : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="p-3">Department</th><th className="p-3">Head</th><th className="p-3">SubHead</th><th className="p-3">QA tester</th><th className="p-3">Shown at sign-up</th><th className="p-3">Status</th><th className="p-3" /></tr>
            </thead>
            <tbody>
              {depts.data?.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 last:border-0">
                  <td className="p-3">
                    {editing?.id === d.id ? (
                      <div className="flex gap-2">
                        <Input value={editing.name} onChange={(e) => setEditing({ id: d.id, name: e.target.value })} className="max-w-48" />
                        <Button onClick={() => patch.mutate({ id: d.id, body: { name: editing.name } })}>Save</Button>
                        <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
                      </div>
                    ) : (
                      <>
                        <div className="font-medium">{d.name} {d.is_system && <Badge>System</Badge>}</div>
                        <div className="text-xs text-slate-500">{d.code}</div>
                      </>
                    )}
                  </td>
                  <td className="p-3">
                    <Select className="max-w-56" value={d.head_employee_id ?? ""} onChange={(e) => setHead.mutate({ id: d.id, head: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">No head</option>
                      {emps.data?.items.filter((e) => e.is_active || e.id === d.head_employee_id).map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                    </Select>
                  </td>
                  <td className="p-3">
                    <Select className="max-w-56" value={d.sub_head_employee_id ?? ""} onChange={(e) => setSubHead.mutate({ id: d.id, subhead: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">No subhead</option>
                      {emps.data?.items.filter((e) => e.is_active || e.id === d.sub_head_employee_id).map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                    </Select>
                  </td>
                  <td className="p-3">
                    {d.is_system ? <span className="text-slate-400">—</span> : (
                      <Select className="max-w-56" aria-label={`QA tester for ${d.name}`} value={d.qa_employee_id ?? ""} onChange={(e) => setQa.mutate({ id: d.id, qa: e.target.value ? Number(e.target.value) : null })}>
                        <option value="">No QA step</option>
                        {emps.data?.items.filter((e) => e.is_active || e.id === d.qa_employee_id).map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                      </Select>
                    )}
                  </td>
                  <td className="p-3">
                    {d.is_system ? <span className="text-slate-400">—</span> : (
                      <input type="checkbox" aria-label={`Show ${d.name} at sign-up`} checked={d.self_service} onChange={(e) => patch.mutate({ id: d.id, body: { self_service: e.target.checked } })} />
                    )}
                  </td>
                  <td className="p-3"><Badge tone={d.is_active ? "green" : "grey"}>{d.is_active ? "Active" : "Inactive"}</Badge></td>
                  <td className="whitespace-nowrap p-3 text-right">
                    {!d.is_system && <Button variant="ghost" onClick={() => setManagingLeaders(d)}>Leaders</Button>}
                    {!d.is_system && editing?.id !== d.id && <Button variant="ghost" onClick={() => setEditing({ id: d.id, name: d.name })}>Rename</Button>}
                    {!d.is_system && <Button variant="ghost" onClick={() => patch.mutate({ id: d.id, body: { is_active: !d.is_active } })}>{d.is_active ? "Deactivate" : "Activate"}</Button>}
                    {!d.is_system && <Button variant="ghost" className="text-red-600" onClick={() => confirm(`Delete ${d.name}? This only works for an empty department.`) && del.mutate(d.id)}>Delete</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {managingLeaders && (
        <ManageLeadersModal
          dept={managingLeaders}
          emps={emps.data?.items ?? []}
          onClose={() => setManagingLeaders(null)}
          onSaved={() => {
            setManagingLeaders(null);
            setNotice("Department leaders updated successfully.");
            refresh();
          }}
        />
      )}
    </>
  );
}

function ManageLeadersModal({ dept, emps, onClose, onSaved }: { dept: Dept; emps: Emp[]; onClose: () => void; onSaved: () => void }) {
  const [headIds, setHeadIds] = useState<number[]>(dept.head_employee_ids ?? (dept.head_employee_id ? [dept.head_employee_id] : []));
  const [subHeadIds, setSubHeadIds] = useState<number[]>(dept.sub_head_employee_ids ?? (dept.sub_head_employee_id ? [dept.sub_head_employee_id] : []));
  const [search, setSearch] = useState("");

  const filtered = emps.filter((e) => e.is_active && e.full_name.toLowerCase().includes(search.toLowerCase()));

  const save = useMutation({
    mutationFn: () => api(`/departments/${dept.id}/leaders`, {
      method: "PUT",
      body: { head_employee_ids: headIds, sub_head_employee_ids: subHeadIds },
    }),
    onSuccess: onSaved,
  });

  const toggleHead = (id: number) => setHeadIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const toggleSubHead = (id: number) => setSubHeadIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg p-5">
        <h2 className="text-base font-semibold text-brand-ink">Manage Leaders for {dept.name}</h2>
        <p className="mt-1 text-xs text-slate-500">Multiple Heads and SubHeads can exist in a department. An employee can hold both Head and SubHead roles.</p>
        <Input className="my-3 text-xs" placeholder="Filter employees..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="max-h-60 overflow-y-auto space-y-2 rounded-lg border border-hairline p-2">
          {filtered.map((e) => (
            <div key={e.id} className="flex items-center justify-between rounded p-1.5 hover:bg-slate-50 text-xs">
              <span className="font-medium text-slate-800">{e.full_name}</span>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-1 cursor-pointer">
                  <input type="checkbox" checked={headIds.includes(e.id)} onChange={() => toggleHead(e.id)} />
                  <span>Head</span>
                </label>
                <label className="flex items-center gap-1 cursor-pointer">
                  <input type="checkbox" checked={subHeadIds.includes(e.id)} onChange={() => toggleSubHead(e.id)} />
                  <span>SubHead</span>
                </label>
              </div>
            </div>
          ))}
          {filtered.length === 0 && <p className="text-xs text-slate-400 p-2">No matching employees.</p>}
        </div>
        <div className="mt-4 flex items-center justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={save.isPending} onClick={() => save.mutate()}>Save Leaders</Button>
        </div>
        <ErrorNote error={save.error} />
      </Card>
    </div>
  );
}
