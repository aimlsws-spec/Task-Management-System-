import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const POLL_MS = 4_000; // unread-count poll: every 4 seconds

export type Notice = { id: number; event_type: string; title: string; body: string; task_id: number | null; reasons: string[]; urgent: boolean; is_read: boolean; created_at: string };
export type NoticePage = { items: Notice[]; total: number; unread: number };

export function ago(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function NotificationBell() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  // The unread count is polled over plain REST (no WebSocket). One query = one timer, however many components read it.
  // The bell only exists while someone is signed in, so polling stops by itself on logout; it also stops after a 401
  // (the session ended and could not be refreshed), and it backs off after other errors instead of hammering the server.
  const count = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => api<{ unread: number }>("/notifications/unread-count"),
    refetchInterval: (q) => (q.state.error instanceof ApiError && q.state.error.status === 401 ? false : q.state.error ? 60_000 : POLL_MS),
    refetchIntervalInBackground: false, // a hidden tab does not poll
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    retry: (n, err) => !(err instanceof ApiError && err.status === 401) && n < 2,
  });
  const latest = useQuery({ queryKey: ["notifications", "latest"], queryFn: () => api<NoticePage>("/notifications", { params: { page_size: 8 } }), enabled: open, staleTime: 0, refetchInterval: open ? 4_000 : false, refetchOnMount: "always" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const read = useMutation({ mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "PUT" }), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: refresh });
  const unread = count.data?.unread ?? 0;

  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div className="relative" ref={box}>
      <button onClick={() => setOpen(!open)} aria-label={`Notifications, ${unread} unread`} className="relative rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900">
        <Bell size={20} aria-hidden />
        {unread > 0 && <span className="absolute -right-0.5 -top-0.5 min-w-5 rounded-full bg-red-600 px-1 text-center text-[11px] font-semibold leading-5 text-white">{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div className="pop-in absolute right-0 z-50 mt-2 w-96 max-w-[92vw] overflow-hidden rounded-xl border border-hairline bg-white shadow-pop">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-sm font-semibold">Notifications</span>
            <button className="text-xs text-indigo-600 hover:underline disabled:opacity-40" disabled={unread === 0} onClick={() => readAll.mutate()}>Mark all read</button>
          </div>
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
            {latest.data?.items.map((n) => (
              <li key={n.id}>
                <button
                  onClick={() => { if (!n.is_read) read.mutate(n.id); setOpen(false); if (n.task_id) nav(`/tasks/${n.task_id}`); }}
                  className={cn("block w-full px-4 py-2.5 text-left hover:bg-slate-50", !n.is_read && "bg-indigo-50/50")}
                >
                  <div className="flex items-start gap-2">
                    {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-indigo-600" aria-label="unread" />}
                    <div className="min-w-0">
                      <div className={cn("truncate text-sm", n.is_read ? "text-slate-700" : "font-semibold")}>{n.urgent && <span className="mr-1 text-red-600">●</span>}{n.title}</div>
                      <div className="line-clamp-2 text-xs text-slate-500">{n.body}</div>
                      <div className="mt-0.5 text-[11px] text-slate-400">{ago(n.created_at)}</div>
                    </div>
                  </div>
                </button>
              </li>
            ))}
            {latest.data?.items.length === 0 && <li className="px-4 py-6 text-center text-sm text-slate-500">You are all caught up.</li>}
          </ul>
          <Link to="/notifications" onClick={() => setOpen(false)} className="block border-t border-slate-100 px-4 py-2.5 text-center text-sm text-indigo-600 hover:bg-slate-50">See all notifications</Link>
        </div>
      )}
    </div>
  );
}
