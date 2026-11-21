import { BUILD_LABEL } from "@/lib/api";
import type { ReactNode } from "react";

export const LOGO = "/seawind-logo.png";

/** SeaWind-branded shell shared by Login, Forgot password and Change password. */
export function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel (desktop) */}
      <aside className="relative hidden overflow-hidden bg-gradient-to-br from-indigo-950 via-indigo-900 to-indigo-600 text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        {/* Echoes the bracket motif in the logo */}
        <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-3xl border-[14px] border-white/10 [border-bottom-color:transparent] [border-left-color:transparent]" />
        <div aria-hidden className="pointer-events-none absolute -bottom-28 -left-20 h-96 w-96 rounded-3xl border-[14px] border-white/10 [border-right-color:transparent] [border-top-color:transparent]" />
        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(white_1px,transparent_1px)] [background-size:100%_28px]" />

        <img src={LOGO} alt="SeaWind – Regeneration of IT Services" className="relative w-56 drop-shadow-xl" />

        <div className="relative max-w-md">
          <span className="inline-block rounded-md bg-white/15 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.14em] text-white ring-1 ring-white/25">
            Regeneration of IT Services
          </span>
          <h1 className="mt-5 text-5xl font-semibold leading-[1.08] tracking-tight">Assign. Track. Deliver.</h1>
          <p className="mt-4 text-base leading-relaxed text-indigo-100">
            One place for SeaWind to assign work, follow progress, measure real effort and keep every deadline accountable.
          </p>
        </div>

        <div className="relative text-xs text-indigo-200"><p>© {new Date().getFullYear()} SeaWind. All rights reserved.</p><p className="mt-1 opacity-60">{BUILD_LABEL}</p></div>
      </aside>

      {/* Form panel */}
      <main className="page-enter flex flex-col items-center justify-center bg-page px-5 py-10 sm:px-10">
        <img src={LOGO} alt="SeaWind" className="mb-6 w-40 lg:hidden" />
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-semibold tracking-tight text-brand-ink">{title}</h2>
          {subtitle && <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-7 rounded-2xl border border-hairline bg-white p-7 shadow-pop">{children}</div>
          <p className="mt-6 text-center text-xs text-slate-400 lg:hidden">© {new Date().getFullYear()} SeaWind</p>
        </div>
      </main>
    </div>
  );
}
