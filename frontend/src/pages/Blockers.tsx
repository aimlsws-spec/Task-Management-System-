import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, PageHeader, Select, Spinner } from "@/components/ui";
import { BlockerCard, type Blocker } from "@/components/Collab";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";

type Page = { items: Blocker[]; total: number };

export function Blockers() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["blockers", status], queryFn: () => api<Page>(`/blockers${status ? `?status=${status}` : ""}`), refetchInterval: 5000 });
  const changed = () => { for (const k of ["blockers", "task", "tasks", "dashboard"]) qc.invalidateQueries({ queryKey: [k] }); };
  return (
    <>
      <PageHeader title="Blockers" subtitle="Problems that are holding up work in your area. Acknowledge them, assign someone to solve them, or escalate." />
      <div className="mb-4 max-w-xs">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">Open (needs attention)</option>
          <option value="resolved">Resolved, awaiting confirmation</option>
          <option value="closed">Closed</option>
        </Select>
      </div>
      {q.isLoading && <Spinner />}
      {q.data && q.data.items.length === 0 && <Card className="p-6 text-sm text-slate-500">Nothing here. When someone reports a blocker it appears in this list straight away.</Card>}
      <ul className="space-y-3">
        {q.data?.items.map((b) => (
          <div key={b.id}>
            <BlockerCard b={b} tz={me?.user.timezone} onChanged={changed} showTask />
            <div className="mt-1 text-xs"><Link className="text-indigo-600 hover:underline" to={`/tasks/${b.task.id}`}>Open the task →</Link></div>
          </div>
        ))}
      </ul>
    </>
  );
}
