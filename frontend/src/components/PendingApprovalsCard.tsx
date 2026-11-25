import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, Clock, FolderGit2, Network, UserCheck, X } from "lucide-react";
import { useState } from "react";
import { Button, Card, Field, Input, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

type PendingApplicant = {
  id: number;
  user_id: number;
  full_name: string;
  email: string;
  company_id: number;
  company_name: string | null;
  department_id?: number | null;
  department_name?: string | null;
  status: string;
  created_at: string | null;
};

type Department = { id: number; name: string; code: string; company_id?: number | null };
type EmployeeItem = {
  id: number;
  full_name: string;
  job_title: string | null;
  company_id: number;
  department_id: number | null;
  employee_code?: string;
  email?: string;
};

export function PendingApprovalsCard({
  companyId,
  compact = false,
  onActionComplete,
}: {
  companyId?: string | number;
  compact?: boolean;
  onActionComplete?: () => void;
}) {
  const qc = useQueryClient();
  const [activeActionId, setActiveActionId] = useState<number | null>(null);
  const [feedbackMsg, setFeedbackMsg] = useState<{ id: number; text: string; type: "success" | "error" } | null>(null);

  // Modal state for approving and setting hierarchy
  const [reviewingApplicant, setReviewingApplicant] = useState<PendingApplicant | null>(null);
  const [selectedDeptId, setSelectedDeptId] = useState<string>("");
  const [selectedReportsToId, setSelectedReportsToId] = useState<string>("");
  const [jobTitle, setJobTitle] = useState<string>("Team Member");

  const { data } = useQuery({
    queryKey: ["employees", "pending-approvals", companyId || "all"],
    queryFn: () =>
      api<PendingApplicant[]>("/employees/pending-approvals", {
        params: companyId ? { company_id: companyId } : undefined,
      }),
  });

  const departmentsQuery = useQuery({
    queryKey: ["departments"],
    queryFn: () => api<Department[]>("/departments"),
  });
  const allDepartments = departmentsQuery.data || [];

  const employeesQuery = useQuery({
    queryKey: ["employees", "active-directory"],
    queryFn: () => api<{ items: EmployeeItem[] }>("/employees?status=active&page_size=200"),
  });
  const allEmployees = employeesQuery.data?.items || [];

  const approveMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: { department_id?: number; reports_to_id?: number; job_title?: string };
    }) => api(`/employees/${id}/approve`, { method: "POST", body }),
    onMutate: ({ id }) => setActiveActionId(id),
    onSuccess: (_res, { id }) => {
      setFeedbackMsg({ id, text: "Approved! Employee access granted and placed in hierarchy.", type: "success" });
      setTimeout(() => setFeedbackMsg(null), 3500);
      qc.invalidateQueries({ queryKey: ["employees"] });
      setReviewingApplicant(null);
      onActionComplete?.();
    },
    onError: (err: any, { id }) => {
      setFeedbackMsg({ id, text: err?.message || "Failed to approve applicant.", type: "error" });
    },
    onSettled: () => setActiveActionId(null),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: number) => api(`/employees/${id}/reject`, { method: "POST" }),
    onMutate: (id) => setActiveActionId(id),
    onSuccess: (_res, id) => {
      setFeedbackMsg({ id, text: "Application declined.", type: "success" });
      setTimeout(() => setFeedbackMsg(null), 3500);
      qc.invalidateQueries({ queryKey: ["employees"] });
      onActionComplete?.();
    },
    onError: (err: any, id) => {
      setFeedbackMsg({ id, text: err?.message || "Failed to decline applicant.", type: "error" });
    },
    onSettled: () => setActiveActionId(null),
  });

  const openApprovalModal = (applicant: PendingApplicant) => {
    setReviewingApplicant(applicant);
    setSelectedDeptId(applicant.department_id ? String(applicant.department_id) : "");
    setSelectedReportsToId("");
    setJobTitle("Team Member");
  };

  const handleConfirmApproval = () => {
    if (!reviewingApplicant) return;
    approveMutation.mutate({
      id: reviewingApplicant.id,
      body: {
        department_id: selectedDeptId ? Number(selectedDeptId) : undefined,
        reports_to_id: selectedReportsToId ? Number(selectedReportsToId) : undefined,
        job_title: jobTitle.trim() || "Team Member",
      },
    });
  };

  const applicants = data ?? [];

  if (applicants.length === 0) {
    if (compact) return null;
    return (
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 text-center shadow-sm">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
          <UserCheck size={20} />
        </div>
        <div className="mt-2 text-sm font-semibold text-slate-800">No Pending Join Requests</div>
        <p className="mt-1 text-xs text-slate-500">
          When candidates sign up selecting your company, they will appear here for leadership approval.
        </p>
      </div>
    );
  }

  // Filter department and manager candidates for the modal
  const modalCompanyId = reviewingApplicant ? reviewingApplicant.company_id : undefined;
  const eligibleDepartments = allDepartments.filter(
    (d) => d.company_id === modalCompanyId || !d.company_id
  );
  const eligibleManagers = allEmployees.filter(
    (e) => e.company_id === modalCompanyId && (!reviewingApplicant || e.id !== reviewingApplicant.id)
  );

  return (
    <>
      <div className="rounded-2xl border border-amber-300/90 bg-gradient-to-r from-amber-50/90 via-orange-50/50 to-amber-50/80 p-4 shadow-sm space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200/60 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-500 text-white font-bold text-xs shadow-sm">
              <Clock size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-slate-900 tracking-tight">
                  Pending Team Join Requests
                </span>
                <span className="inline-flex items-center rounded-full bg-amber-200/90 px-2 py-0.5 text-[11px] font-bold text-amber-900 shadow-xs">
                  {applicants.length} awaiting decision
                </span>
              </div>
              <p className="text-xs text-slate-600">
                Approve to place applicant in the hierarchy and grant workspace access, or decline to deny entry.
              </p>
            </div>
          </div>
        </div>

        <div className="divide-y divide-amber-200/50 space-y-2">
          {applicants.map((a) => {
            const isBusy = activeActionId === a.id;
            const msg = feedbackMsg?.id === a.id ? feedbackMsg : null;

            return (
              <div
                key={a.id}
                className="flex flex-wrap items-center justify-between gap-3 pt-2 first:pt-0"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs">
                    {a.full_name
                      ? a.full_name
                          .split(" ")
                          .map((n) => n[0])
                          .join("")
                          .toUpperCase()
                          .slice(0, 2)
                      : "U"}
                  </div>
                  <div className="space-y-0.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900">{a.full_name}</span>
                      <span className="inline-flex items-center gap-1 rounded-md bg-white/90 px-2 py-0.5 text-[11px] font-medium text-slate-700 border border-slate-200 shadow-xs">
                        <Building2 size={12} className="text-indigo-600" />
                        {a.company_name || `Company #${a.company_id}`}
                      </span>
                      {a.department_name && (
                        <span className="inline-flex items-center gap-1 rounded-md bg-amber-100/90 px-2 py-0.5 text-[11px] font-medium text-amber-900 border border-amber-300/80 shadow-xs">
                          <FolderGit2 size={12} className="text-amber-700" />
                          {a.department_name}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <span>{a.email}</span>
                      {a.created_at && (
                        <>
                          <span>•</span>
                          <span>{new Date(a.created_at).toLocaleDateString()}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {msg ? (
                    <span
                      className={`text-xs font-semibold ${
                        msg.type === "success" ? "text-emerald-700" : "text-rose-700"
                      }`}
                    >
                      {msg.text}
                    </span>
                  ) : (
                    <>
                      <Button
                        type="button"
                        disabled={isBusy}
                        onClick={() => openApprovalModal(a)}
                        className="inline-flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-xs transition-colors"
                      >
                        <Check size={14} />
                        {isBusy && approveMutation.isPending ? "Approving…" : "Approve & Set Hierarchy"}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={isBusy}
                        onClick={() => {
                          if (confirm(`Decline join request for ${a.full_name} (${a.email})?`)) {
                            rejectMutation.mutate(a.id);
                          }
                        }}
                        className="inline-flex items-center gap-1.5 text-rose-700 hover:bg-rose-100/80 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition-colors"
                      >
                        <X size={14} />
                        {isBusy && rejectMutation.isPending ? "Declining…" : "Decline"}
                      </Button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Leadership Approval & Hierarchy Modal */}
      {reviewingApplicant && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <Card className="w-full max-w-lg p-6 shadow-2xl bg-white border border-slate-200 rounded-2xl animate-in fade-in-50 zoom-in-95">
            <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Approve Join Request & Assign Hierarchy
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Confirm department placement and assign direct manager for{" "}
                  <strong className="text-slate-800">{reviewingApplicant.full_name}</strong> ({reviewingApplicant.email}).
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReviewingApplicant(null)}
                className="text-slate-400 hover:text-slate-600 rounded-lg p-1 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div className="rounded-lg bg-slate-50 p-3 text-xs border border-slate-200/80 flex items-center justify-between">
                <div>
                  <span className="text-slate-500 font-medium">Target Company:</span>{" "}
                  <span className="font-semibold text-slate-800">
                    {reviewingApplicant.company_name || `Company #${reviewingApplicant.company_id}`}
                  </span>
                </div>
                {reviewingApplicant.department_name && (
                  <div>
                    <span className="text-slate-500 font-medium">Requested Dept:</span>{" "}
                    <span className="font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                      {reviewingApplicant.department_name}
                    </span>
                  </div>
                )}
              </div>

              <Field label="Assigned Department">
                <Select
                  value={selectedDeptId}
                  onChange={(e) => setSelectedDeptId(e.target.value)}
                  className="w-full"
                >
                  <option value="">Select department…</option>
                  {eligibleDepartments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.code})
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Set in Hierarchy (Direct Manager / Supervisor)">
                <Select
                  value={selectedReportsToId}
                  onChange={(e) => setSelectedReportsToId(e.target.value)}
                  className="w-full"
                >
                  <option value="">Default (Department Head / Top Level Manager)</option>
                  {eligibleManagers.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.full_name} {m.job_title ? `— ${m.job_title}` : ""} {m.employee_code ? `(${m.employee_code})` : ""}
                    </option>
                  ))}
                </Select>
                <p className="mt-1 text-[11px] text-slate-500 flex items-center gap-1">
                  <Network size={12} className="text-indigo-600" />
                  The approved person will report to this supervisor in the organization tree and submit work to them.
                </p>
              </Field>

              <Field label="Job Title / Designation">
                <Input
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  placeholder="e.g. AI/ML Developer, Software Engineer, Support Agent"
                />
              </Field>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <Button
                variant="ghost"
                type="button"
                disabled={approveMutation.isPending}
                onClick={() => setReviewingApplicant(null)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={approveMutation.isPending}
                onClick={handleConfirmApproval}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold shadow-xs"
              >
                {approveMutation.isPending ? (
                  <span className="flex items-center gap-1.5">
                    <Spinner /> Approving…
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <Check size={16} /> Confirm Approval & Place in Hierarchy
                  </span>
                )}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
