import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { ago, type NoticePage } from "@/components/NotificationBell";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Pref = { event_type: string; label: string; channels: string[]; locked: boolean; in_app: boolean; email: boolean };

const dayLabel = (iso: string) => {
  const d = new Date(iso), t = new Date();
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, t)) return "Today";
  if (same(d, new Date(t.getTime() - 86_400_000))) return "Yesterday";
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

export function Notifications() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [tab, setTab] = useState<"all" | "unread" | "settings">("all");
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: ["notifications", "list", tab, page],
    queryFn: () => api<NoticePage>("/notifications", { params: { unread: tab === "unread" ? "true" : undefined, page, page_size: 30 } }),
    enabled: tab !== "settings",
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const read = useMutation({ mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "PUT" }), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: refresh });

  const groups = new Map<string, NoticePage["items"]>();
  for (const n of list.data?.items ?? []) {
    const k = dayLabel(n.created_at);
    groups.set(k, [...(groups.get(k) ?? []), n]);
  }
  const tabBtn = (id: typeof tab, label: string) => (
    <button onClick={() => { setTab(id); setPage(1); }} className={cn("rounded-lg px-3 py-1.5 text-sm font-medium", tab === id ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100")}>{label}</button>
  );

  return (
    <>
      <PageHeader title="Notifications" subtitle="Everything you have been told about, newest first."
        actions={tab !== "settings" && <Button variant="outline" disabled={!list.data?.unread || readAll.isPending} onClick={() => readAll.mutate()}>Mark all read</Button>} />
      <div className="mb-4 flex gap-1">{tabBtn("all", "All")}{tabBtn("unread", `Unread${list.data ? ` (${list.data.unread})` : ""}`)}{tabBtn("settings", "Settings")}</div>
      {tab === "settings" ? <Preferences /> : list.isLoading ? <Spinner /> : (
        <div className="space-y-5">
          {[...groups.entries()].map(([day, items]) => (
            <div key={day}>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{day}</h2>
              <Card className="divide-y divide-slate-100">
                {items.map((n) => (
                  <button key={n.id} onClick={() => { if (!n.is_read) read.mutate(n.id); if (n.task_id) nav(`/tasks/${n.task_id}`); }}
                    className={cn("block w-full px-4 py-3 text-left hover:bg-slate-50", !n.is_read && "bg-indigo-50/50")}>
                    <div className="flex items-start gap-3">
                      <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.is_read ? "bg-transparent" : "bg-indigo-600")} />
                      <div className="min-w-0 flex-1">
                        <div className={cn("text-sm", !n.is_read && "font-semibold")}>{n.urgent && <Badge tone="red">Urgent</Badge>} {n.title}</div>
                        <div className="text-sm text-slate-600">{n.body}</div>
                        <div className="mt-1 text-xs text-slate-400">{ago(n.created_at)} · {n.reasons.map((r) => r.replace(/_/g, " ").toLowerCase()).join(", ")}</div>
                      </div>
                    </div>
                  </button>
                ))}
              </Card>
            </div>
          ))}
          {list.data?.items.length === 0 && <Card className="p-8 text-center text-sm text-slate-500">{tab === "unread" ? "No unread notifications." : "Nothing yet."}</Card>}
          {list.data && list.data.total > 30 * page && <Button variant="outline" onClick={() => setPage(page + 1)}>Load older</Button>}
        </div>
      )}
    </>
  );
}

function Preferences() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notifications", "prefs"], queryFn: () => api<Pref[]>("/me/notification-preferences") });
  const set = useMutation({
    mutationFn: (v: { event_type: string; channel: "in_app" | "email"; enabled: boolean }) => api("/me/notification-preferences", { method: "PUT", body: v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications", "prefs"] }),
  });
  if (q.isLoading) return <Spinner />;
  return (
    <Card className="overflow-x-auto">
      <p className="p-4 pb-0 text-sm text-slate-600">Choose how you hear about each kind of event. Notices that are part of your responsibility (for example a new task for you, or an overdue deadline) are mandatory and cannot be switched off.</p>
      <table className="mt-3 w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500"><tr><th className="p-3">Event</th><th className="p-3 text-center">In the app</th><th className="p-3 text-center">By email</th></tr></thead>
        <tbody>
          {q.data?.map((p) => (
            <tr key={p.event_type} className="border-b border-slate-100 last:border-0">
              <td className="p-3">{p.label} {p.locked && <Badge>Mandatory</Badge>}</td>
              {(["in_app", "email"] as const).map((ch) => (
                <td key={ch} className="p-3 text-center">
                  {p.channels.includes(ch) ? (
                    <input type="checkbox" aria-label={`${p.label} ${ch}`} checked={p[ch]} disabled={p.locked || set.isPending} onChange={(e) => set.mutate({ event_type: p.event_type, channel: ch, enabled: e.target.checked })} />
                  ) : <span className="text-slate-300">—</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="p-3"><ErrorNote error={set.error} /></div>
    </Card>
  );
}
