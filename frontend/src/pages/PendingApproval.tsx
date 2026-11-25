import { useState } from "react";
import { Building2, Clock, LogOut, RefreshCw } from "lucide-react";
import { AuthLayout } from "@/components/AuthLayout";
import { Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export function PendingApproval() {
  const { me, reload, logout } = useAuth();
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const fullName = me?.employee?.full_name || me?.user?.email || "Team Member";
  const email = me?.user?.email;
  const companyName = me?.employee?.company_name || "SeaWind Solution";

  async function handleCheckStatus() {
    setChecking(true);
    try {
      await reload();
      setCheckedAt(new Date());
    } finally {
      setChecking(false);
    }
  }

  return (
    <AuthLayout
      title="Awaiting Approval"
      subtitle={`Your registration request to join ${companyName} is under leadership review.`}
    >
      <div className="space-y-6">
        {/* Status indicator banner */}
        <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4 text-amber-900">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-white shadow-sm">
              <Clock size={20} className="animate-pulse" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-tight text-amber-950">Approval Pending</span>
                <span className="inline-flex items-center rounded-full bg-amber-200/80 px-2 py-0.5 text-[11px] font-semibold text-amber-900">
                  Leadership Review
                </span>
              </div>
              <p className="text-xs text-amber-800 leading-relaxed">
                Your request to join has been dispatched to the company's CEO and Owner. You will be granted full employee access as soon as leadership approves it.
              </p>
            </div>
          </div>
        </div>

        {/* Application details box */}
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Request Information
          </div>
          <div className="divide-y divide-slate-100 text-sm">
            <div className="flex justify-between py-2">
              <span className="text-slate-500">Target Company</span>
              <span className="font-semibold text-slate-900 flex items-center gap-1.5">
                <Building2 size={15} className="text-indigo-600" />
                {companyName}
              </span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-slate-500">Full Name</span>
              <span className="font-medium text-slate-900">{fullName}</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-slate-500">Email Address</span>
              <span className="font-medium text-slate-900">{email}</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-slate-500">Account Status</span>
              <span className="inline-flex items-center gap-1 font-semibold text-amber-600">
                <span>⏳</span> Pending CEO / Owner Decision
              </span>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="space-y-2.5">
          <Button
            type="button"
            onClick={handleCheckStatus}
            disabled={checking}
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white flex items-center justify-center gap-2 shadow-sm"
          >
            <RefreshCw size={16} className={checking ? "animate-spin" : ""} />
            {checking ? "Checking approval status…" : "Check Approval Status"}
          </Button>

          {checkedAt && (
            <div className="text-center text-[11px] text-slate-500">
              Last checked at {checkedAt.toLocaleTimeString()}. Still awaiting approval.
            </div>
          )}

          <Button
            type="button"
            variant="ghost"
            onClick={() => logout()}
            className="w-full py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 flex items-center justify-center gap-2"
          >
            <LogOut size={16} /> Sign out
          </Button>
        </div>
      </div>
    </AuthLayout>
  );
}
