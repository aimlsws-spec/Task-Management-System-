import { AlertTriangle, BarChart3, ScrollText, Bell, OctagonAlert, BellRing, Building2, FolderKanban, Gauge, LayoutDashboard, ListChecks, LogOut, MailCheck, Menu, ShieldCheck, Users, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { NotificationBell } from "@/components/NotificationBell";

type Item = { to: string; label: string; icon: LucideIcon };

// The org structure (departments, hierarchy, roles) is fixed company setup, not a day-to-day screen:
// it lives in an "Administration" section that only users holding management permissions see.
// Navigation is a UI convenience; the API enforces access on every call.
function useNav() {
  const { me, can } = useAuth();
  const main: Item[] = [{ to: "/", label: "Dashboard", icon: LayoutDashboard }, { to: "/notifications", label: "Notifications", icon: Bell }];
  // Work screens: everyone who can see tasks; people who assign work also get the workload view.
  if (can("task.view")) main.push({ to: "/tasks", label: me?.permissions["task.view"] === "self" ? "My Tasks" : "Tasks", icon: ListChecks });
  if (can("blocker.view") && me?.permissions["blocker.view"] !== "self") main.push({ to: "/blockers", label: "Blockers", icon: OctagonAlert });
  if (can("delay.review")) main.push({ to: "/delays", label: "Delays & Extensions", icon: AlertTriangle });
  if (can("task.assign")) main.push({ to: "/workload", label: "Team Workload", icon: Gauge });
  if (can("task.view")) main.push({ to: "/projects", label: "Projects", icon: FolderKanban }); // everyone sees the projects they are part of
  if (can("report.view")) main.push({ to: "/reports", label: "Reports", icon: BarChart3 });

  const admin: Item[] = [];
  if (can("employee.manage")) {
    // Users with task access (such as Owner) have Owner Panel as main dashboard, so provide Admin Panel link here
    if (can("task.view")) {
      admin.push({ to: "/admin", label: "Admin Panel", icon: LayoutDashboard });
    }
    admin.push({ to: "/companies", label: "Companies", icon: Building2 });
    admin.push({ to: "/employees", label: "Employees", icon: Users });
  }
  if (can("employee.manage")) admin.push({ to: "/role-emails", label: "Role emails", icon: MailCheck });
  if (can("department.manage")) admin.push({ to: "/departments", label: "Departments", icon: Building2 });
  if (can("role.manage")) admin.push({ to: "/roles", label: "Roles & Permissions", icon: ShieldCheck });
  if (can("notification.rules.manage")) admin.push({ to: "/admin/notifications", label: "Notifications & Jobs", icon: BellRing });
  if (can("audit.view")) admin.push({ to: "/audit", label: "Audit log", icon: ScrollText }); // always the last Administration tab

  // Managers / department heads get a read-only list of the people they work with (e.g. to assign tasks).
  const scope = me?.permissions["employee.view"];
  if (!can("employee.manage") && (scope === "team" || scope === "department")) {
    main.push({ to: "/employees", label: scope === "department" ? "My Department" : "My Team", icon: Users });
  }
  return { main, admin };
}

const link = ({ isActive }: { isActive: boolean }) =>
  cn(
    "group relative flex items-center gap-2.5 rounded-lg px-3 py-3 text-sm font-medium transition-colors md:py-2",
    isActive ? "bg-indigo-50 text-indigo-700 before:absolute before:-left-3 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-r-full before:bg-indigo-600" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  );

function Section({ title, items }: { title?: string; items: Item[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-0.5">
      {title && <div className="px-3 pb-1.5 pt-5 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">{title}</div>}
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} end={to === "/"} className={link}>
          <Icon size={17} strokeWidth={1.75} aria-hidden className="shrink-0 opacity-80 group-hover:opacity-100" /> {label}
        </NavLink>
      ))}
    </div>
  );
}

function initials(name?: string | null) {
  const parts = (name ?? "?").split(/[\s@.]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[1][0] : "")).toUpperCase();
}

// Copies each column heading onto its cells (data-label) so the phone card layout (index.css) can show it.
function useStackedTables(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const label = () => {
      el.querySelectorAll("table").forEach((t) => {
        const heads = Array.from(t.querySelectorAll("thead th")).map((h) => h.textContent?.trim() ?? "");
        if (!heads.length) return;
        t.querySelectorAll("tbody tr").forEach((tr) => {
          let i = 0;
          Array.from(tr.children).forEach((c) => {
            const td = c as HTMLElement;
            if (td.tagName === "TD" && !td.hasAttribute("data-label")) td.setAttribute("data-label", heads[i] ?? "");
            i += (td as HTMLTableCellElement).colSpan || 1;
          });
        });
      });
    };
    label();
    const mo = new MutationObserver(label);
    mo.observe(el, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [root]);
}

export function AppShell() {
  const { me, logout } = useAuth();
  const { main, admin } = useNav();
  // Tab title shows who is signed in, so several roles open at once are easy to tell apart.
  useEffect(() => {
    const who = me?.employee?.full_name ?? me?.user.email;
    document.title = who ? `${who} · SeaWind` : "SeaWind Task Management";
  }, [me]);

  const mainRef = useRef<HTMLElement>(null);
  useStackedTables(mainRef);
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setMenuOpen(false), [pathname]); // close the phone menu after choosing a page
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const sidebar = (
    <>
      <nav className="flex-1 overflow-y-auto px-3 pb-4" aria-label="Main">
        <Section items={main} />
        <Section title="Administration" items={admin} />
      </nav>
      <div className="border-t border-hairline p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <div aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-indigo-800 text-xs font-semibold text-white shadow-card">{initials(me?.employee?.full_name ?? me?.user.email)}</div>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-900">{me?.employee?.full_name ?? me?.user.email}</div>
            <div className="truncate text-xs capitalize text-slate-500">{me?.roles.map((r) => r.replace("_", " ")).join(", ")}</div>
          </div>
        </div>
        <button onClick={logout} className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900">
          <LogOut size={16} strokeWidth={1.75} aria-hidden /> Sign out
        </button>
      </div>
    </>
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-hairline bg-white md:flex">
        <div className="px-5 pb-3 pt-5">
          <img src="/seawind-logo.png" alt="SeaWind" className="w-36" />
        </div>
        {sidebar}
      </aside>
      {menuOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setMenuOpen(false)} />
          <aside className="safe-top safe-bottom absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-white shadow-xl">
            <div className="flex items-center justify-between px-5 pb-3 pt-4">
              <img src="/seawind-logo.png" alt="SeaWind" className="w-32" />
              <button onClick={() => setMenuOpen(false)} aria-label="Close menu" className="grid h-10 w-10 place-items-center rounded-lg text-slate-600 hover:bg-slate-100"><X size={20} /></button>
            </div>
            {sidebar}
          </aside>
        </div>
      )}
      <main ref={mainRef} className="min-w-0 flex-1 overflow-y-auto">
        <div className="safe-top sticky top-0 z-30 bg-white/80 backdrop-blur-md">
          <div className="flex items-center justify-between gap-2 border-b border-hairline bg-white/80 px-4 py-1.5 backdrop-blur-md md:justify-end md:px-8">
            <button onClick={() => setMenuOpen(true)} aria-label="Open menu" aria-expanded={menuOpen} className="grid h-10 w-10 place-items-center rounded-lg text-slate-700 hover:bg-slate-100 md:hidden"><Menu size={22} /></button>
            <img src="/seawind-logo.png" alt="SeaWind" className="h-7 md:hidden" />
            <NotificationBell />
          </div>
        </div>
        <div className="safe-bottom mx-auto max-w-6xl p-4 pb-10 md:p-8 md:pb-16">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
