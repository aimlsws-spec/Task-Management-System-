import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { RequestRow } from "@/components/TaskAccountability";
import { EscalationBadge, fmtDay, PriorityChip, WHY, type DelayQueue, type ExtensionReq } from "@/components/task-ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Everything late that needs a manager: who has not explained, explanations to decide on, extension requests. */
export function DelayReviews() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const tz = me?.user.timezone;
  const leadership = !!me?.roles.some((r) => r === "owner" || r === "ceo");
  const q = useQuery({ queryKey: ["delays", "queue"], queryFn: () => api<DelayQueue>("/delays/queue") });
  const reqs = useQuery({ queryKey: ["extension-requests"], queryFn: () => api<ExtensionReq[]>("/extension-requests") });
  const accept = useMutation({
    mutationFn: (id: number) => api(`/delay-reasons/${id}/review`, { body: { decision: "accepted" } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["delays"] }); qc.invalidateQueries({ queryKey: ["tasks"] }); },
  });

  if (q.isLoading) return <Spinner />;
  const d = q.data ?? { missing: [], awaiting: [] };
  return (
    <>
      <PageHeader title="Delays & extensions" subtitle={leadership ? "Delay reasons the Department Heads and Manager escalated to you. Accepting never completes a task." : "Late work in your scope. Approve a reason to share it with the CEO and Owner; accepting never completes a task: it stays open until the work is done."} />
      <div className="space-y-5">
        <Card className="overflow-x-auto">
          <div className="p-4 pb-0"><h2 className="text-sm font-semibold">Overdue with no valid explanation <Badge tone={d.missing.length ? "red" : "grey"}>{d.missing.length}</Badge></h2></div>
          <table className="mt-2 w-full text-left text-sm">
            <tbody>
              {d.missing.map((m) => (
                <tr key={m.task_id} className="border-t border-slate-100">
                  <td className="p-3"><Link to={`/tasks/${m.task_id}`} className="font-medium hover:underline">{m.title}</Link><div className="text-xs text-slate-500">{m.task_no} · {m.assignee}</div></td>
                  <td className="p-3"><PriorityChip priority={m.priority} /></td>
                  <td className="whitespace-nowrap p-3 text-xs text-red-700">due {fmtDay(m.due_at, tz)}</td>
                  <td className="p-3 text-xs text-slate-600">{WHY[m.why]?.replace("Your manager asked", "Manager asked").replace("your last", "their last") ?? m.why}</td>
                  <td className="p-3"><EscalationBadge level={m.escalation_level} /></td>
                </tr>
              ))}
              {d.missing.length === 0 && <tr><td className="p-6 text-center text-slate-500">Everyone who is late has explained.</td></tr>}
            </tbody>
          </table>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold">Explanations waiting for your decision <Badge tone={d.awaiting.length ? "orange" : "grey"}>{d.awaiting.length}</Badge></h2>
          <ul className="mt-3 space-y-3">
            {d.awaiting.map((a) => (
              <li key={a.task_id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/tasks/${a.task_id}`} className="font-medium hover:underline">{a.title}</Link>
                  <span className="text-xs text-slate-500">{a.task_no} · {a.assignee} · due {fmtDay(a.due_at, tz)}</span>
                  <EscalationBadge level={a.escalation_level} />
                  {a.extension_count > 0 && <Badge tone="orange">Extended ×{a.extension_count}</Badge>}
                </div>
                <p className="mt-1 text-slate-800">{a.explanation.reason}</p>
                <p className="mt-1 text-xs text-slate-500">{a.explanation.progress_pct}% done · remaining: {a.explanation.remaining_work} · expected {fmtDay(a.explanation.expected_completion_at, tz)}</p>
                <div className="mt-2 flex gap-2">
                  <Button className="py-1" disabled={accept.isPending} onClick={() => accept.mutate(a.explanation.id)}>{leadership ? "Accept" : "Approve & share with CEO/Owner"}</Button>
                  <Link to={`/tasks/${a.task_id}`}><Button variant="outline" className="py-1">Open to decide otherwise</Button></Link>
                </div>
              </li>
            ))}
            {d.awaiting.length === 0 && <li className="text-sm text-slate-500">Nothing is waiting.</li>}
          </ul>
          <div className="mt-2"><ErrorNote error={accept.error} /></div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold">Extension requests <Badge tone={reqs.data?.length ? "orange" : "grey"}>{reqs.data?.length ?? 0}</Badge></h2>
          <ul className="mt-3 space-y-3">
            {reqs.data?.map((r) => (
              <li key={r.id}>
                <div className="mb-1 text-sm"><Link to={`/tasks/${r.task_id}`} className="font-medium hover:underline">{r.title}</Link> <span className="text-xs text-slate-500">{r.task_no} · {r.assignee}</span></div>
                <RequestRow r={r} tz={tz} canDecide />
              </li>
            ))}
            {reqs.data?.length === 0 && <li className="text-sm text-slate-500">No pending requests.</li>}
          </ul>
        </Card>
      </div>
    </>
  );
}
