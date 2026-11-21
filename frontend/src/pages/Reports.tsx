import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { Button, Card, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api, apiDownload } from "@/lib/api";

type Report = { name: string; title: string; columns: string[]; rows: Record<string, unknown>[]; summary: Record<string, unknown> };

const label = (c: string) => c.replace(/_/g, " ");
const cell = (v: unknown) => (v === null || v === undefined ? "" : typeof v === "boolean" ? (v ? "yes" : "no") : String(v));

/** Eight reports, each limited to the viewer's scope, with CSV / Excel export. Active hours and elapsed time are never merged. */
export function ReportsPage() {
  const cat = useQuery({ queryKey: ["reports"], queryFn: () => api<{ name: string; title: string }[]>("/reports") });
  const [name, setName] = useState("completion");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [priority, setPriority] = useState("");
  const params = { date_from: from, date_to: to, priority };
  const rep = useQuery({ queryKey: ["report", name, from, to, priority], queryFn: () => api<Report>(`/reports/${name}`, { params }) });
  const [err, setErr] = useState<unknown>(null);
  const dl = async (format: "csv" | "xlsx") => {
    setErr(null);
    const qs = new URLSearchParams({ format, ...(from && { date_from: from }), ...(to && { date_to: to }), ...(priority && { priority }) });
    try { await apiDownload(`/reports/${name}/export?${qs}`, `tms-${name}.${format}`); } catch (e) { setErr(e); }
  };
  return (
    <>
      <PageHeader title="Reports" subtitle="Everything here is limited to the people you are responsible for." />
      <Card className="p-4">
        <div className="grid gap-3 sm:grid-cols-5">
          <Field label="Report">
            <Select value={name} onChange={(e) => setName(e.target.value)}>{cat.data?.map((r) => <option key={r.name} value={r.name}>{r.title}</option>)}</Select>
          </Field>
          <Field label="From"><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
          <Field label="To"><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
          <Field label="Priority">
            <Select value={priority} onChange={(e) => setPriority(e.target.value)}><option value="">Any</option>{["critical", "high", "medium", "low"].map((p) => <option key={p}>{p}</option>)}</Select>
          </Field>
          <div className="flex items-end gap-2">
            <Button variant="outline" onClick={() => dl("csv")}><Download size={14} aria-hidden /> CSV</Button>
            <Button variant="outline" onClick={() => dl("xlsx")}><Download size={14} aria-hidden /> Excel</Button>
          </div>
        </div>
        <ErrorNote error={err} />
      </Card>
      {rep.isLoading && <Spinner />}
      {rep.data && (
        <Card className="mt-4 overflow-x-auto">
          <div className="flex flex-wrap gap-x-6 gap-y-1 p-4 pb-2 text-sm">
            <b>{rep.data.title}</b>
            {Object.entries(rep.data.summary).map(([k, v]) => <span key={k} className="text-slate-600 capitalize">{label(k)}: <b>{cell(v) || "–"}</b></span>)}
          </div>
          <table data-no-stack className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs capitalize text-slate-500"><tr>{rep.data.columns.map((c) => <th key={c} className="whitespace-nowrap p-2.5">{label(c)}</th>)}</tr></thead>
            <tbody>
              {rep.data.rows.map((r, i) => <tr key={i} className="border-t border-slate-100">{rep.data!.columns.map((c) => <td key={c} className="p-2.5">{cell(r[c])}</td>)}</tr>)}
              {rep.data.rows.length === 0 && <tr><td colSpan={rep.data.columns.length} className="p-6 text-center text-slate-500">No data for these filters.</td></tr>}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
