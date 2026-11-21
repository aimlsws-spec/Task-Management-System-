import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex select-none items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-[background-color,box-shadow,transform,border-color] duration-150 active:translate-y-px disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-indigo-600 text-white shadow-[0_1px_2px_rgb(16_24_40/0.18),inset_0_1px_0_rgb(255_255_255/0.14)] hover:bg-indigo-700",
        outline: "border border-slate-200 bg-white text-slate-700 shadow-card hover:border-slate-300 hover:bg-slate-50",
        ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
        danger: "bg-red-600 text-white shadow-[0_1px_2px_rgb(16_24_40/0.18),inset_0_1px_0_rgb(255_255_255/0.14)] hover:bg-red-700",
      },
    },
    defaultVariants: { variant: "primary" },
  },
);

export function Button({ className, variant, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>) {
  return <button className={cn(button({ variant }), className)} {...p} />;
}

export function Input({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-card transition-[border-color,box-shadow] placeholder:text-slate-400 hover:border-slate-300 focus:border-indigo-500 focus:outline-none focus:ring-4 focus:ring-indigo-100",
        className,
      )}
      {...p}
    />
  );
}

export function Select({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-card transition-[border-color,box-shadow] hover:border-slate-300 focus:border-indigo-500 focus:outline-none focus:ring-4 focus:ring-indigo-100", className)}
      {...p}
    />
  );
}

export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-slate-700">{label}</span>
      {children}
      {error && <span role="alert" className="block text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-xl border border-hairline bg-white shadow-card", className)}>{children}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="page-enter mb-7 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-brand-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-prose text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

const tone = {
  grey: "bg-slate-100 text-slate-700",
  blue: "bg-blue-100 text-blue-700",
  green: "bg-green-100 text-green-700",
  red: "bg-red-100 text-red-700",
  orange: "bg-orange-100 text-orange-700",
  purple: "bg-purple-100 text-purple-700",
  indigo: "bg-indigo-100 text-indigo-700",
} as const;

export function Badge({ tone: t = "grey", children }: { tone?: keyof typeof tone; children: ReactNode }) {
  return <span className={cn("inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-black/5", tone[t])}>{children}</span>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
      {error instanceof Error ? error.message : "Something went wrong"}
    </p>
  );
}

/** Loading placeholder: calm shimmering rows instead of bare text. */
export function Spinner() {
  return (
    <div role="status" aria-label="Loading" className="space-y-3 p-5">
      <div className="skeleton h-4 w-1/3" />
      <div className="skeleton h-3.5 w-full" />
      <div className="skeleton h-3.5 w-11/12" />
      <div className="skeleton h-3.5 w-4/5" />
    </div>
  );
}

/** Friendly empty state for lists and panels. */
export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      {icon && <div className="grid h-10 w-10 place-items-center rounded-full bg-slate-100 text-slate-500">{icon}</div>}
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {hint && <p className="max-w-sm text-xs text-slate-500">{hint}</p>}
    </div>
  );
}
