import { ShieldCheck } from "lucide-react";
import { Card } from "@/components/ui";
import { fmtDateTime, type Task } from "@/components/task-ui";

/** Who is accountable above the assignee: the Department Head, and any Head who has taken ownership of this task. */
export function OwnershipCard({ t, tz }: { t: Task; tz?: string }) {
  const owners = t.ownership ?? [];
  if (!t.accountable_head && owners.length === 0) return null;
  return (
    <Card className="p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={16} aria-hidden /> Accountability</h2>
      {t.accountable_head?.full_name && <p className="mt-2 text-sm">Department Head in the loop: <b>{t.accountable_head.full_name}</b></p>}
      {owners.length === 0 ? (
        <p className="mt-1 text-xs text-slate-500">No Head has taken ownership of this task yet.</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm">
          {owners.map((o) => (
            <li key={o.employee_id}><b>{o.full_name}</b> took ownership <span className="text-xs text-slate-400">· {fmtDateTime(o.at, tz)}</span>{o.note && <p className="text-slate-600">{o.note}</p>}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
