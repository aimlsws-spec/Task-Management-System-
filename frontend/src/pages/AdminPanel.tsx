import { useAuth } from "@/lib/auth";
import { AdminDashboard } from "@/components/AdminDashboard";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

export function AdminPanel() {
  const { me } = useAuth();
  const name = me?.employee?.full_name ?? me?.user.email;
  const isOwner = me?.roles?.includes("owner");

  return (
    <div className="space-y-4">
      {isOwner && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-200 bg-indigo-50/80 px-4 py-3 text-sm text-indigo-950 shadow-sm">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-base text-white shadow-sm">👑</span>
            <div>
              <div className="font-semibold text-indigo-900">Owner System Administration</div>
              <div className="text-xs text-indigo-700">You are accessing the Admin Panel with full system owner privileges.</div>
            </div>
          </div>
          <Link
            to="/?panel=owner"
            className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3.5 py-1.5 text-xs font-semibold text-indigo-700 border border-indigo-200 shadow-sm hover:bg-indigo-50 hover:text-indigo-800 transition-colors"
          >
            <ArrowLeft size={14} /> Back to Owner Executive Panel
          </Link>
        </div>
      )}
      <AdminDashboard name={name} />
    </div>
  );
}
