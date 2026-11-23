import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus, UserCheck, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Company = {
  id: number;
  name: string;
  code: string;
  logo_url: string | null;
  is_active: boolean;
  created_at: string;
};

type CompanyCEO = {
  user_id: number;
  email: string;
  full_name: string;
  job_title: string | null;
  employee_code: string | null;
  granted_at: string;
};

type EmployeeOption = {
  id: number;
  user_id: number;
  full_name: string;
  email: string;
  roles: string[];
};

export function Companies() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const isOwner = me?.roles?.includes("owner");
  const isAdmin = me?.roles?.includes("admin");

  const [showAddModal, setShowAddModal] = useState(false);
  const [newCompany, setNewCompany] = useState({ name: "", code: "", logo_url: "", ceo_user_id: "", ceo_email: "" });

  const [assignCeoCompId, setAssignCeoCompId] = useState<number | null>(null);
  const [selectedCeoUserId, setSelectedCeoUserId] = useState<string>("");
  const [ceoInviteEmail, setCeoInviteEmail] = useState<string>("");

  const companiesQuery = useQuery({
    queryKey: ["companies"],
    queryFn: () => api<Company[]>("/companies"),
  });

  const employeesQuery = useQuery({
    queryKey: ["employees-all"],
    queryFn: () => api<{ items: EmployeeOption[] }>("/employees", { params: { page_size: 200 } }),
    enabled: isOwner || isAdmin,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["companies"] });
  };

  const createCompany = useMutation({
    mutationFn: () =>
      api<Company>("/companies", {
        body: {
          name: newCompany.name.trim(),
          code: newCompany.code.trim().toUpperCase(),
          logo_url: newCompany.logo_url.trim() || null,
          ceo_user_id: newCompany.ceo_user_id ? Number(newCompany.ceo_user_id) : null,
          ceo_email: newCompany.ceo_email.trim() || null,
        },
      }),
    onSuccess: () => {
      setNewCompany({ name: "", code: "", logo_url: "", ceo_user_id: "", ceo_email: "" });
      setShowAddModal(false);
      invalidate();
    },
  });

  const assignCeo = useMutation({
    mutationFn: ({ companyId, userId, email }: { companyId: number; userId?: number | null; email?: string | null }) =>
      api(`/companies/${companyId}/ceos`, {
        body: {
          user_id: userId ?? null,
          email: email ?? null,
        },
      }),
    onSuccess: () => {
      setSelectedCeoUserId("");
      setCeoInviteEmail("");
      setAssignCeoCompId(null);
      invalidate();
    },
  });

  const removeCeo = useMutation({
    mutationFn: ({ companyId, userId }: { companyId: number; userId: number }) =>
      api(`/companies/${companyId}/ceos/${userId}`, {
        method: "DELETE",
      }),
    onSuccess: invalidate,
  });

  const potentialCeos = (employeesQuery.data?.items ?? []).filter(
    (e) => e.roles.includes("ceo") || e.roles.includes("owner") || isOwner
  );

  return (
    <>
      <PageHeader
        title="Companies"
        subtitle="Multi-company administration. The Owner has overall authority across all companies and can authorize CEOs to manage specific companies."
        actions={
          isOwner && (
            <Button onClick={() => setShowAddModal(true)}>
              <Plus size={16} className="mr-1 inline" /> Add Company
            </Button>
          )
        }
      />

      <ErrorNote error={createCompany.error ?? assignCeo.error ?? removeCeo.error} />

      {/* Add Company Modal */}
      {showAddModal && (
        <Card className="mb-6 border-indigo-200 bg-indigo-50/40 p-5 shadow-sm">
          <div className="flex items-center justify-between pb-3">
            <h3 className="font-semibold text-slate-900">Add New Company</h3>
            <button
              type="button"
              onClick={() => setShowAddModal(false)}
              className="text-slate-400 hover:text-slate-600"
            >
              <X size={18} />
            </button>
          </div>
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              createCompany.mutate();
            }}
            className="grid gap-3 sm:grid-cols-3"
          >
            <Field label="Company Name">
              <Input
                required
                minLength={2}
                placeholder="e.g. Acme Corporation"
                value={newCompany.name}
                onChange={(e) => setNewCompany({ ...newCompany, name: e.target.value })}
              />
            </Field>
            <Field label="Company Code">
              <Input
                required
                minLength={2}
                placeholder="e.g. ACME"
                value={newCompany.code}
                onChange={(e) => setNewCompany({ ...newCompany, code: e.target.value })}
              />
            </Field>
            <Field label="Logo URL (optional)">
              <Input
                placeholder="https://..."
                value={newCompany.logo_url}
                onChange={(e) => setNewCompany({ ...newCompany, logo_url: e.target.value })}
              />
            </Field>
            <Field label="Appoint CEO (existing user)">
              <Select
                value={newCompany.ceo_user_id}
                onChange={(e) => setNewCompany({ ...newCompany, ceo_user_id: e.target.value, ceo_email: "" })}
                className="text-xs"
              >
                <option value="">None / Or invite by email below</option>
                {potentialCeos.map((p) => (
                  <option key={p.user_id} value={p.user_id}>
                    {p.full_name} ({p.email})
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Or Invite CEO by Email">
              <Input
                type="email"
                placeholder="ceo@company.com (activation link sent)"
                value={newCompany.ceo_email}
                disabled={Boolean(newCompany.ceo_user_id)}
                onChange={(e) => setNewCompany({ ...newCompany, ceo_email: e.target.value })}
              />
            </Field>
            <div className="sm:col-span-3 flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createCompany.isPending}>
                {createCompany.isPending ? "Creating…" : "Create Company"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Companies List */}
      <div className="space-y-4">
        {companiesQuery.isLoading ? (
          <Spinner />
        ) : !companiesQuery.data?.length ? (
          <EmptyState
            icon={<Building2 size={24} />}
            title="No companies found"
            hint="Create a company using the button above."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {companiesQuery.data.map((company) => (
              <CompanyCard
                key={company.id}
                company={company}
                isOwner={!!isOwner}
                potentialCeos={potentialCeos}
                assignCeoCompId={assignCeoCompId}
                setAssignCeoCompId={setAssignCeoCompId}
                selectedCeoUserId={selectedCeoUserId}
                setSelectedCeoUserId={setSelectedCeoUserId}
                ceoInviteEmail={ceoInviteEmail}
                setCeoInviteEmail={setCeoInviteEmail}
                onAssignCeo={(arg) => assignCeo.mutate({ companyId: company.id, ...arg })}
                onRemoveCeo={(userId) => removeCeo.mutate({ companyId: company.id, userId })}
                isAssigning={assignCeo.isPending}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function CompanyCard({
  company,
  isOwner,
  potentialCeos,
  assignCeoCompId,
  setAssignCeoCompId,
  selectedCeoUserId,
  setSelectedCeoUserId,
  ceoInviteEmail,
  setCeoInviteEmail,
  onAssignCeo,
  onRemoveCeo,
  isAssigning,
}: {
  company: Company;
  isOwner: boolean;
  potentialCeos: EmployeeOption[];
  assignCeoCompId: number | null;
  setAssignCeoCompId: (id: number | null) => void;
  selectedCeoUserId: string;
  setSelectedCeoUserId: (id: string) => void;
  ceoInviteEmail: string;
  setCeoInviteEmail: (email: string) => void;
  onAssignCeo: (arg: { userId?: number; email?: string }) => void;
  onRemoveCeo: (userId: number) => void;
  isAssigning: boolean;
}) {
  const ceosQuery = useQuery({
    queryKey: ["company-ceos", company.id],
    queryFn: () => api<CompanyCEO[]>(`/companies/${company.id}/ceos`),
  });

  const isAssigningThis = assignCeoCompId === company.id;

  return (
    <Card className="p-5 flex flex-col justify-between">
      <div>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 font-bold text-sm">
              {company.code.slice(0, 3)}
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">{company.name}</h3>
              <p className="text-xs text-slate-500 font-mono">Code: {company.code}</p>
            </div>
          </div>
          <Badge tone={company.is_active ? "green" : "grey"}>
            {company.is_active ? "Active" : "Inactive"}
          </Badge>
        </div>

        {/* Authorized CEOs Section */}
        <div className="mt-4 border-t border-slate-100 pt-3">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
            <span>Authorized CEOs</span>
            {isOwner && !isAssigningThis && (
              <button
                type="button"
                onClick={() => {
                  setAssignCeoCompId(company.id);
                  setSelectedCeoUserId("");
                }}
                className="text-indigo-600 hover:text-indigo-800 font-medium lowercase"
              >
                + add CEO
              </button>
            )}
          </div>

          {ceosQuery.isLoading ? (
            <Spinner />
          ) : ceosQuery.data && ceosQuery.data.length > 0 ? (
            <div className="space-y-1.5">
              {ceosQuery.data.map((ceo) => (
                <div
                  key={ceo.user_id}
                  className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <UserCheck size={14} className="text-indigo-600" />
                    <span className="font-medium text-slate-900">{ceo.full_name}</span>
                    <span className="text-slate-400 font-mono">({ceo.email})</span>
                  </div>
                  {isOwner && (
                    <button
                      type="button"
                      onClick={() =>
                        confirm(`Revoke CEO access for ${ceo.full_name} on ${company.name}?`) &&
                        onRemoveCeo(ceo.user_id)
                      }
                      className="text-slate-400 hover:text-red-600 ml-2"
                      title="Revoke access"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400 italic">No authorized CEO assigned yet.</p>
          )}

          {/* Assign CEO Form */}
          {isOwner && isAssigningThis && (
            <div className="mt-2.5 rounded-lg border border-indigo-200 bg-indigo-50/50 p-2.5 space-y-2">
              <div className="text-xs font-medium text-slate-700">
                Authorize CEO for {company.name}:
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                <Select
                  value={selectedCeoUserId}
                  onChange={(e) => {
                    setSelectedCeoUserId(e.target.value);
                    if (e.target.value) setCeoInviteEmail("");
                  }}
                  className="text-xs min-w-44 flex-1"
                >
                  <option value="">Select existing user / CEO…</option>
                  {potentialCeos.map((p) => (
                    <option key={p.user_id} value={p.user_id}>
                      {p.full_name} ({p.email})
                    </option>
                  ))}
                </Select>
                <span className="text-xs text-slate-400">or</span>
                <Input
                  type="email"
                  placeholder="Invite new CEO email…"
                  value={ceoInviteEmail}
                  onChange={(e) => {
                    setCeoInviteEmail(e.target.value);
                    if (e.target.value) setSelectedCeoUserId("");
                  }}
                  className="text-xs min-w-44 flex-1"
                />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button
                  className="py-1 px-3 text-xs"
                  variant="outline"
                  onClick={() => {
                    setAssignCeoCompId(null);
                    setSelectedCeoUserId("");
                    setCeoInviteEmail("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  className="py-1 px-3 text-xs"
                  disabled={(!selectedCeoUserId && !ceoInviteEmail.trim()) || isAssigning}
                  onClick={() => {
                    if (selectedCeoUserId) {
                      onAssignCeo({ userId: Number(selectedCeoUserId) });
                    } else if (ceoInviteEmail.trim()) {
                      onAssignCeo({ email: ceoInviteEmail.trim() });
                    }
                  }}
                >
                  {ceoInviteEmail.trim() ? "Send CEO Invite" : "Authorize CEO"}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 pt-2 border-t border-slate-100 text-[11px] text-slate-400 flex justify-between">
        <span>ID: {company.id}</span>
        <span>Added {new Date(company.created_at).toLocaleDateString()}</span>
      </div>
    </Card>
  );
}
