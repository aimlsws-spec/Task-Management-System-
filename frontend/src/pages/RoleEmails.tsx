import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

type Invite = { id: number; email: string; role_code: string; role_name: string; claimed: boolean; claimed_at: string | null; created_at: string };

// Admin accounts are never created here; department heads are named on the Departments page.
const ROLES = [
  { value: "owner", label: "Owner" },
  { value: "ceo", label: "CEO" },
  { value: "manager", label: "Manager" },
  { value: "department_head", label: "Department Head" },
  { value: "employee", label: "Employee" },
];

/** Administration > Role emails: register the email of the Owner, CEO, Manager... Whoever signs up with exactly that
 *  email gets the role automatically. Everyone else who signs up is an Employee. */
export function RoleEmails() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("owner");
  const list = useQuery({ queryKey: ["role-invites"], queryFn: () => api<Invite[]>("/role-invites") });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["role-invites"] }); qc.invalidateQueries({ queryKey: ["employees"] }); };
  const add = useMutation({
    mutationFn: () => api("/role-invites", { body: { email, role_code: role } }),
    onSuccess: () => { setEmail(""); refresh(); },
  });
  const [resent, setResent] = useState<number | null>(null);
  const resend = useMutation({ mutationFn: (id: number) => api(`/role-invites/${id}/resend`, { method: "POST" }), onSuccess: (_r, id) => { setResent(id); refresh(); } });
  const revoke = useMutation({ mutationFn: (id: number) => api(`/role-invites/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const submit = (e: FormEvent) => { e.preventDefault(); add.mutate(); };

  return (
    <>
      <PageHeader
        title="Role emails"
        subtitle="Register the email of each Owner, CEO or Manager. When that person signs up with exactly this email, they receive the role automatically. Anyone else who signs up becomes an Employee."
      />
      <Card className="mb-5 p-5">
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <Field label="Email"><Input type="email" required className="w-72" placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Role">
            <Select value={role} onChange={(e) => setRole(e.target.value)} className="w-48">
              {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </Select>
          </Field>
          <Button type="submit" disabled={add.isPending}>Register email</Button>
        </form>
        <p className="mt-3 text-xs text-slate-500">
          Owner, CEO and Manager skip the department questions and join Management. The CEO reports to the Owner; a Manager reports to the CEO.
          Share the sign-up link only with the right person: whoever signs up with the registered email first gets the role.
          If that person already has an account, the role is added to it now and they must sign in again.
        </p>
        <div className="mt-3"><ErrorNote error={add.error ?? revoke.error ?? resend.error} /></div>
      </Card>

      <Card className="overflow-x-auto">
        {list.isLoading ? <Spinner /> : !list.data?.length ? (
          <EmptyState icon={<MailCheck size={18} />} title="No role emails yet" hint="Register your Owner and CEO emails above so they can sign up and land in the right role." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead><tr><th className="p-3">Email</th><th className="p-3">Role</th><th className="p-3">Status</th><th className="p-3" /></tr></thead>
            <tbody>
              {list.data.map((i) => (
                <tr key={i.id}>
                  <td className="p-3 font-medium">{i.email}</td>
                  <td className="p-3"><Badge tone="indigo">{i.role_name}</Badge></td>
                  <td className="p-3">{i.claimed ? <Badge tone="green">Signed up</Badge> : <Badge tone="orange">Waiting for sign-up</Badge>}</td>
                  <td className="p-3 text-right">
                    {!i.claimed && <Button variant="ghost" disabled={resend.isPending} onClick={() => resend.mutate(i.id)}>{resent === i.id ? "Sent again ✓" : "Resend email"}</Button>}
                    {!i.claimed && <Button variant="ghost" className="text-red-600" onClick={() => confirm(`Remove ${i.email}? They will sign up as a normal Employee.`) && revoke.mutate(i.id)}>Remove</Button>}
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
