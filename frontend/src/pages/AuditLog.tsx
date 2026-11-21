import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, Field, Input, PageHeader, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/components/task-ui";
import { useAuth } from "@/lib/auth";

type Row = { id: number; actor_user_id: number | null; action: string; entity_type: string; entity_id: string; before: unknown; after: unknown; ip: string | null; created_at: string };
type Page = { items: Row[]; total: number; page: number; page_size: number };

/** Append-only record of who did what. Read-only. */
export function AuditLogPage() {
  const { me } = useAuth();
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["audit", action, entity, page], queryFn: () => api<Page>("/admin/audit-logs", { params: { action: action || undefined, entity_type: entity || undefined, page, page_size: 50 } }) });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.page_size)) : 1;
  return (
    <>
      <PageHeader title="Audit log" subtitle="Every important action is recorded here and cannot be edited or deleted." />
      <Card className="p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Action (exact, e.g. TASK_CREATED)"><Input value={action} onChange={(e) => { setAction(e.target.value.trim()); setPage(1); }} placeholder="Any" /></Field>
          <Field label="Entity (task, user…)"><Input value={entity} onChange={(e) => { setEntity(e.target.value.trim()); setPage(1); }} placeholder="Any" /></Field>
        </div>
      </Card>
      {q.isLoading ? <Spinner /> : (
        <Card className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="p-2.5">When</th><th>Action</th><th>Entity</th><th>User #</th><th>Details</th></tr></thead>
            <tbody>
              {q.data?.items.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 align-top">
                  <td className="whitespace-nowrap p-2.5 text-xs">{fmtDateTime(r.created_at, me?.user.timezone)}</td>
                  <td className="font-medium">{r.action}</td>
                  <td>{r.entity_type} #{r.entity_id}</td>
                  <td>{r.actor_user_id ?? "system"}</td>
                  <td className="max-w-md break-words p-2.5 text-xs text-slate-600">{r.after ? JSON.stringify(r.after) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between p-3 text-xs text-slate-500">
            <span>{q.data?.total ?? 0} entries</span>
            <span className="flex items-center gap-2">
              <Button variant="outline" className="py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              Page {page} of {pages}
              <Button variant="outline" className="py-1" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </span>
          </div>
        </Card>
      )}
    </>
  );
}
