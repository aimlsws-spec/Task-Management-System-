import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailCheck, Network, Send } from "lucide-react";
import { useState, useMemo, useEffect, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Invite = {
  id: number;
  email: string;
  role_code: string;
  role_name: string;
  company_id?: number | null;
  company_name?: string | null;
  department_id?: number | null;
  department_name?: string | null;
  claimed: boolean;
  claimed_at: string | null;
  created_at: string;
};

type Company = { id: number; name: string; code: string };
type Department = { id: number; name: string; code: string; company_id?: number | null };

// Admin accounts are never created here; department heads are named on the Departments page.
const ALL_ROLES = [
  { value: "owner", label: "Owner" },
  { value: "ceo", label: "CEO" },
  { value: "manager", label: "Manager" },
  { value: "department_head", label: "Department Head" },
  { value: "sub_head", label: "Department SubHead" },
  { value: "employee", label: "Employee" },
];

/** Employee & Role Invitations: register the email of each Owner, CEO, Manager or Employee.
 *  When that person signs up with this email, they receive their role, company and department automatically. */
export function RoleEmails() {
  const { me, can } = useAuth();
  const isOwner = me?.roles?.includes("owner");
  const isAdmin = me?.roles?.includes("admin");
  const isCeo = me?.roles?.includes("ceo") && !isOwner && !isAdmin;

  const allowedRoles = useMemo(() => {
    if (isCeo) {
      return ALL_ROLES.filter((r) => ["manager", "department_head", "sub_head", "employee"].includes(r.value));
    }
    return ALL_ROLES;
  }, [isCeo]);

  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(isCeo ? "employee" : "owner");
  const [companyId, setCompanyId] = useState<string>("");
  const [departmentId, setDepartmentId] = useState<string>("");

  const companiesQuery = useQuery({
    queryKey: ["companies"],
    queryFn: () => api<Company[]>("/companies"),
  });
  const companies = companiesQuery.data || [];

  const departmentsQuery = useQuery({
    queryKey: ["departments"],
    queryFn: () => api<Department[]>("/departments"),
  });
  const allDepartments = departmentsQuery.data || [];

  useEffect(() => {
    if (companies.length > 0 && !companyId) {
      setCompanyId(String(companies[0].id));
    }
  }, [companies, companyId]);

  const activeCompanyId = Number(companyId) || (companies.length > 0 ? companies[0].id : 1);

  const companyDepartments = useMemo(() => {
    return allDepartments.filter((d) => d.company_id === activeCompanyId || !d.company_id);
  }, [allDepartments, activeCompanyId]);

  useEffect(() => {
    if (companyDepartments.length > 0 && !departmentId) {
      setDepartmentId(String(companyDepartments[0].id));
    }
  }, [companyDepartments, departmentId]);

  const handleCompanyChange = (newCid: string) => {
    setCompanyId(newCid);
    const cidNum = Number(newCid);
    const depts = allDepartments.filter((d) => d.company_id === cidNum || !d.company_id);
    setDepartmentId(depts.length > 0 ? String(depts[0].id) : "");
  };

  const isManagementRole = ["owner", "ceo"].includes(role);

  const list = useQuery({ queryKey: ["role-invites"], queryFn: () => api<Invite[]>("/role-invites") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["role-invites"] });
    qc.invalidateQueries({ queryKey: ["employees"] });
  };

  const add = useMutation({
    mutationFn: () =>
      api("/role-invites", {
        body: {
          email,
          role_code: role,
          company_id: activeCompanyId,
          department_id: !isManagementRole && departmentId ? Number(departmentId) : undefined,
        },
      }),
    onSuccess: () => {
      setEmail("");
      refresh();
    },
  });

  const [resent, setResent] = useState<number | null>(null);
  const resend = useMutation({
    mutationFn: (id: number) => api(`/role-invites/${id}/resend`, { method: "POST" }),
    onSuccess: (_r, id) => {
      setResent(id);
      refresh();
    },
  });

  const revoke = useMutation({
    mutationFn: (id: number) => api(`/role-invites/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate();
  };

  return (
    <>
      <PageHeader
        title="Employee & Role Invitations"
        subtitle={
          isCeo
            ? "Invite team members, managers, and staff to your authorized company. They receive their role and company scope upon sign-up."
            : "Register the email of each Owner, CEO, Manager or Employee. When that person signs up or logs in, they receive the role automatically."
        }
        actions={
          can("hierarchy.manage") && (
            <Link
              to="/hierarchy"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
            >
              <Network size={16} /> Employee Hierarchy
            </Link>
          )
        }
      />
      <Card className="mb-5 p-5">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Field label="Email Address">
            <Input
              type="email"
              required
              className="w-72"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Role to Grant">
            <Select value={role} onChange={(e) => setRole(e.target.value)} className="w-48">
              {allowedRoles.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </Select>
          </Field>
          {companies.length > 0 && (
            <Field label="Company">
              <Select value={companyId} onChange={(e) => handleCompanyChange(e.target.value)} className="w-52">
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.code.toUpperCase()})
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {!isManagementRole && (
            <Field label="Department">
              <Select
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}
                className="w-52"
                disabled={companyDepartments.length === 0}
              >
                {companyDepartments.length === 0 ? (
                  <option value="">No departments</option>
                ) : (
                  companyDepartments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))
                )}
              </Select>
            </Field>
          )}
          <Button type="submit" disabled={add.isPending} className="bg-indigo-600 hover:bg-indigo-700 text-white">
            <Send size={15} /> {add.isPending ? "Sending..." : "Send Invitation"}
          </Button>
        </form>
        <p className="mt-3 text-xs text-slate-500">
          Owner and CEO join Management automatically. For staff, department heads, and managers, the selected department and company scope are applied automatically upon sign-up.
          If that person already has an account, the role, company, and department are granted immediately.
        </p>
        <div className="mt-3">
          <ErrorNote error={add.error ?? revoke.error ?? resend.error} />
        </div>
      </Card>

      <Card className="overflow-x-auto">
        {list.isLoading ? (
          <div className="p-8 flex justify-center"><Spinner /></div>
        ) : !list.data?.length ? (
          <EmptyState
            icon={<MailCheck size={18} />}
            title="No invitations sent yet"
            hint="Register your employees, managers, or executives above so they can sign up with direct role assignments."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/75 text-xs uppercase tracking-wider text-slate-500 font-semibold">
                <th className="p-3">Email</th>
                <th className="p-3">Role</th>
                <th className="p-3">Company</th>
                <th className="p-3">Department</th>
                <th className="p-3">Status</th>
                <th className="p-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((i) => (
                <tr key={i.id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="p-3 font-medium text-slate-900">{i.email}</td>
                  <td className="p-3">
                    <Badge tone={i.role_code === "owner" ? "orange" : i.role_code === "ceo" ? "purple" : i.role_code === "manager" ? "indigo" : "grey"}>
                      {i.role_name}
                    </Badge>
                  </td>
                  <td className="p-3 text-xs text-slate-600">
                    {i.company_name || `Company #${i.company_id || 1}`}
                  </td>
                  <td className="p-3 text-xs text-slate-600">
                    {i.department_name || (["owner", "ceo"].includes(i.role_code) ? "Management" : "—")}
                  </td>
                  <td className="p-3">
                    {i.claimed ? <Badge tone="green">Signed up</Badge> : <Badge tone="orange">Waiting for sign-up</Badge>}
                  </td>
                  <td className="p-3 text-right">
                    {!i.claimed && (
                      <Button variant="ghost" disabled={resend.isPending} onClick={() => resend.mutate(i.id)}>
                        {resent === i.id ? "Sent again ✓" : "Resend email"}
                      </Button>
                    )}
                    {!i.claimed && (
                      <Button
                        variant="ghost"
                        className="text-red-600 hover:text-red-700"
                        onClick={() => confirm(`Remove ${i.email}? They will sign up as a normal Employee.`) && revoke.mutate(i.id)}
                      >
                        Remove
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
