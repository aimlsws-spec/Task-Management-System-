import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, Clock, UserCheck, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";

type PendingApplicant = {
  id: number;
  user_id: number;
  full_name: string;
  email: string;
  company_id: number;
  company_name: string | null;
  status: string;
  created_at: string | null;
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

  const { data } = useQuery({
    queryKey: ["employees", "pending-approvals", companyId || "all"],
    queryFn: () =>
      api<PendingApplicant[]>("/employees/pending-approvals", {
        params: companyId ? { company_id: companyId } : undefined,
      }),
  });

  const approveMutation = useMutation({
    mutationFn: (id: number) => api(`/employees/${id}/approve`, { method: "POST" }),
    onMutate: (id) => setActiveActionId(id),
    onSuccess: (_res, id) => {
      setFeedbackMsg({ id, text: "Approved! Employee access granted.", type: "success" });
      setTimeout(() => setFeedbackMsg(null), 3500);
      qc.invalidateQueries({ queryKey: ["employees"] });
      onActionComplete?.();
    },
    onError: (err: any, id) => {
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

  return (
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
              Approve to grant full workspace access, or decline to deny entry.
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
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">{a.full_name}</span>
                    <span className="inline-flex items-center gap-1 rounded-md bg-white/90 px-2 py-0.5 text-[11px] font-medium text-slate-700 border border-slate-200 shadow-xs">
                      <Building2 size={12} className="text-indigo-600" />
                      {a.company_name || `Company #${a.company_id}`}
                    </span>
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
                      onClick={() => approveMutation.mutate(a.id)}
                      className="inline-flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-xs transition-colors"
                    >
                      <Check size={14} />
                      {isBusy && approveMutation.isPending ? "Approving…" : "Approve"}
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
  );
}
