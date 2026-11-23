import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { ACTION_LABEL, fmtDateTime, fmtDay, fmtDuration, OverdueBadge, PriorityChip, statusLabel, StatusBadge, type Task, type Workload } from "@/components/task-ui";
import { useEmployees } from "@/pages/Projects";
import { api, ApiError, apiDownload, apiUpload } from "@/lib/api";
import { ChangeDeadlinePanel, DeadlineCard, DelayGate, DelaySection, ExplainPanel, OverdueBanner, RequestExtensionPanel, ReviewDelayPanel } from "@/components/TaskAccountability";
import { useAuth } from "@/lib/auth";
import { BlockersSection, Discussion, RaiseBlockerPanel } from "@/components/Collab";

type Event = { id: number; action: string; actor: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null; at: string };
type Panel = null | "edit" | "reassign" | "priority" | "cancel" | "hold" | "progress" | "finish" | "submit_to_owner" | "review" | "revert" | "deadline" | "extension" | "explain" | "review_delay" | "blocker";

const textarea = "block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200";
const REASONS = [["qa_defect", "QA found a defect"], ["incomplete", "Work is incomplete"], ["requirement_change", "Requirement changed"], ["other", "Other"]] as const;

function describe(e: Event, people: Map<number, string>) {
  const a = e.after ?? {}, b = e.before ?? {};
  switch (e.action) {
    case "TASK_CREATED": return `Assigned to ${people.get(Number(a.assignee_id)) ?? `#${a.assignee_id}`} · priority ${a.priority}`;
    case "TASK_REASSIGNED": return `${people.get(Number(b.assignee_id)) ?? "previous owner"} → ${people.get(Number(a.assignee_id)) ?? `#${a.assignee_id}`}${a.reason ? ` · ${a.reason}` : ""}`;
    case "TASK_PRIORITY_CHANGED": return `${b.priority} → ${a.priority}${a.reason ? ` · ${a.reason}` : ""}`;
    case "TASK_CANCELLED": case "TASK_ON_HOLD": return String(a.reason ?? "");
    case "TASK_UPDATED": return Object.keys(a).map((k) => k.replace("_", " ")).join(", ");
    case "TASK_ATTACHMENT_ADDED": return String(a.name ?? "");
    case "TASK_PROGRESS": return `${b.progress_pct}% → ${a.progress_pct}% · ${a.note}`;
    case "TASK_COMPLETED": case "TASK_SUBMITTED": return `${a.summary}${a.late ? " · completed after the deadline" : ""}`;
    case "TASK_REVERTED": return `${String(a.reason_code).replace("_", " ")}${a.found_by ? ` (found by ${a.found_by})` : ""} · ${a.reason}`;
    case "TASK_REVIEW_REJECTED": return String(a.reason ?? "");
    case "TIMER_PAUSED": case "TIMER_STOPPED": return fmtDuration(Number(a.seconds));
    default: return "";
  }
}

export function TaskDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const { me } = useAuth();
  const tz = me?.user.timezone;
  const location = useLocation();
  const warnings: string[] = (location.state as { warnings?: string[] } | null)?.warnings ?? [];
  const created = (location.state as { created?: boolean } | null)?.created;
  const [panel, setPanel] = useState<Panel>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const task = useQuery({ queryKey: ["task", id], queryFn: () => api<Task>(`/tasks/${id}`), refetchInterval: 5000 });
  const timeline = useQuery({ queryKey: ["task", id, "timeline"], queryFn: () => api<Event[]>(`/tasks/${id}/timeline`), refetchInterval: 5000 });
  const t = task.data;
  const isLeadership = Boolean(me?.roles.includes("owner") || me?.roles.includes("ceo"));
  const can = (a: string) => !!t?.allowed_actions?.includes(a);
  const iAmAssignee = !!t && me?.employee?.id === t.assignee.id;
  const people = useQuery({ queryKey: ["workload"], queryFn: () => api<Workload[]>("/workload"), enabled: can("reassign") });
  const names = new Map<number, string>(people.data?.map((p) => [p.employee_id, p.full_name]) ?? []);
  if (t) { names.set(t.assignee.id, t.assignee.full_name); names.set(t.assigned_by.id, t.assigned_by.full_name); }

  const refresh = () => {
    for (const k of ["task", "tasks", "workload", "time"]) qc.invalidateQueries({ queryKey: [k] });
    setPanel(null);
  };
  const act = useMutation({
    mutationFn: (v: { path: string; body?: unknown; method?: string }) => api(`/tasks/${id}${v.path}`, { method: v.method ?? "POST", body: v.body ?? (v.method === "PATCH" ? {} : undefined) }),
    onSuccess: refresh,
    // The server decides when a task is late. If it says a reason is needed (the deadline + grace period passed while this page
    // was open), reload the task so the reason box appears and keep what the employee already typed.
    onError: (e) => { if (e instanceof ApiError && e.code === "DELAY_EXPLANATION_REQUIRED") refresh(); },
  });
  const upload = useMutation({ mutationFn: (f: File) => apiUpload(`/tasks/${id}/attachments`, f), onSuccess: refresh });
  const post = (path: string, body?: unknown) => act.mutate({ path, body });
  const reviewDelay = useMutation({
    mutationFn: (b: Record<string, unknown>) => api(`/delay-reasons/${task.data!.delay!.items[0].id}/review`, { body: b }),
    onSuccess: refresh,
  });

  if (task.isLoading) return <Spinner />;
  if (task.error || !t) return <p className="text-sm text-slate-500">This task does not exist or you do not have access to it. <Link to="/tasks" className="text-indigo-600 hover:underline">Back to tasks</Link></p>;

  const toggle = (p: Panel) => setPanel(panel === p ? null : p);
  const dl = t.delay;

  return (
    <>
      <div className="mb-2 text-sm"><Link to="/tasks" className="text-indigo-600 hover:underline">← Tasks</Link></div>
      {created && <p className="mb-3 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">Task assigned. {t.assignee.full_name} will see it in their task list, and everyone above them in the hierarchy can follow it.</p>}
      {warnings.map((w) => <p key={w} className="mb-3 rounded-lg bg-orange-50 px-3 py-2 text-sm text-orange-800">{w}</p>)}
      <OverdueBanner t={t} mine={iAmAssignee} onExplain={() => setPanel("explain")} />
      {iAmAssignee && dl?.required && panel !== "explain" && (
        <DelayGate t={t} onSubmit={(b) => post("/delay-reasons", b)} error={act.error} busy={act.isPending} />
      )}
      <PageHeader
        title={t.title}
        subtitle={`${t.task_no} · assigned by ${t.assigned_by.full_name} on ${fmtDay(t.assigned_at, tz)}`}
        actions={
          <div className="flex flex-wrap justify-end gap-2">
            {can("start") && <Button onClick={() => post("/start", {})}>Start work</Button>}
            {can("progress") && <Button variant="outline" onClick={() => toggle("progress")}>Update progress</Button>}
            {can("complete") && <Button onClick={() => toggle("finish")}>Mark complete</Button>}
            {!can("complete") && can("submit_for_review") && <Button onClick={() => toggle("finish")}>Submit for review</Button>}
            {can("raise_blocker") && <Button variant="outline" onClick={() => toggle("blocker")}>Report a blocker</Button>}
            {can("hold") && <Button variant="outline" onClick={() => toggle("hold")}>Put on hold</Button>}
            {can("unhold") && <Button variant="outline" onClick={() => post("/unhold")}>Resume from hold</Button>}
            {can("review") && <Button onClick={() => toggle("review")}>{t.review_stage === "qa" ? "Test: report bugs or pass" : t.review_stage === "head" ? "Approve work" : "Review"}</Button>}
            {can("verify") && <Button variant="outline" onClick={() => post("/verify", {})}>Verify</Button>}
            {can("revert") && <Button variant="danger" onClick={() => toggle("revert")}>Revert</Button>}
            {isLeadership && can("edit") && <Button variant="outline" onClick={() => toggle("edit")}>Edit</Button>}
            {can("reassign") && <Button variant="outline" onClick={() => toggle("reassign")}>Transfer task</Button>}
            {can("submit_to_owner") && <Button className="bg-indigo-600 hover:bg-indigo-700 text-white" onClick={() => toggle("submit_to_owner")}>Complete & Submit to Owner</Button>}
            {can("change_priority") && <Button variant="outline" onClick={() => toggle("priority")}>Priority</Button>}
            {isLeadership && can("cancel") && <Button variant="danger" onClick={() => toggle("cancel")}>Cancel task</Button>}
            {can("explain_delay") && !dl?.required && <Button variant="outline" onClick={() => toggle("explain")}>Delay update</Button>}
            {can("review_delay") && <Button onClick={() => toggle("review_delay")}>Decide on delay</Button>}
          </div>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusBadge status={t.status} /><PriorityChip priority={t.priority} />{t.is_overdue && <OverdueBadge />}
        {t.requires_review && !t.review_stage && <Badge tone="purple">Review required</Badge>}
        {t.status === "under_review" && t.review_stage === "qa" && (
          <Badge tone="purple">
            Waiting for QA testing: {t.qa_members?.length ? t.qa_members.map((q) => q.full_name).join(", ") : t.qa?.full_name ?? "QA"}
          </Badge>
        )}
        {t.status === "under_review" && t.review_stage === "head" && (
          <Badge tone="purple">
            Waiting for Head / SubHead review: {t.heads && t.heads.length > 0 ? t.heads.map((h) => h.full_name).join(", ") : [t.head?.full_name, t.sub_head?.full_name].filter(Boolean).join(" / ") || "Head"}
          </Badge>
        )}
        {t.heads && t.heads.length > 0 && !t.review_stage ? (
          <Badge tone="grey">Heads: {t.heads.map((h) => h.full_name).join(", ")}</Badge>
        ) : t.head && !t.review_stage ? (
          <Badge tone="grey">Head: {t.head.full_name}</Badge>
        ) : null}
        {t.sub_head && !t.heads?.length && !t.review_stage && <Badge tone="grey">SubHead: {t.sub_head.full_name}</Badge>}
        {t.qa_members && t.qa_members.length > 0 && !t.review_stage ? (
          <Badge tone="grey">QA: {t.qa_members.map((q) => q.full_name).join(", ")}</Badge>
        ) : t.qa && !t.review_stage ? (
          <Badge tone="grey">QA: {t.qa.full_name}</Badge>
        ) : null}
        {t.status === "under_review" && t.review_stage === "leadership" && <Badge tone="purple">Waiting for CEO / Owner review</Badge>}
        {t.project_id && <Link to={`/projects/${t.project_id}`} className="text-xs font-medium text-indigo-600 hover:underline">Project: {t.project ?? "open"}</Link>}
        {t.verified_at && <Badge tone="green">Verified</Badge>}
        {(t.revert_count ?? 0) > 0 && <Badge tone="orange">Reworked ×{t.revert_count}</Badge>}
      </div>

      <ErrorNote error={act.error ?? upload.error} />

      {panel === "edit" && <EditPanel t={t} onSave={(b) => act.mutate({ path: "", method: "PATCH", body: b })} onClose={() => setPanel(null)} />}
      {panel === "reassign" && <ReassignPanel t={t} people={people.data ?? []} onSave={(b) => post("/reassign", b)} onClose={() => setPanel(null)} />}
      {panel === "submit_to_owner" && <SubmitToOwnerPanel onSave={(b) => post("/submit-to-owner", b)} onClose={() => setPanel(null)} />}
      {panel === "priority" && <PriorityPanel t={t} onSave={(b) => post("/priority", b)} onClose={() => setPanel(null)} />}
      {panel === "cancel" && <ReasonPanel title="Cancel this task" label="Reason (required — the assignee and everyone above can see it)" danger cta="Cancel task" onSave={(reason) => post("/cancel", { reason })} onClose={() => setPanel(null)} />}
      {panel === "hold" && <ReasonPanel title="Put this task on hold" label="Why is it on hold?" cta="Put on hold" onSave={(reason) => post("/hold", { reason })} onClose={() => setPanel(null)} />}
      {panel === "progress" && <ProgressPanel t={t} onSave={(b) => post("/progress", b)} onClose={() => setPanel(null)} />}
      {panel === "finish" && <FinishPanel t={t} review={!can("complete")} lateRequired={act.error instanceof ApiError && act.error.code === "DELAY_EXPLANATION_REQUIRED"} onSave={(b) => post(can("complete") ? "/complete" : "/submit-for-review", b)} onClose={() => setPanel(null)} />}
      {panel === "review" && <ReviewPanel stage={t.review_stage ?? null} onSave={(b) => post("/review", b)} onClose={() => setPanel(null)} />}
      {panel === "revert" && <RevertPanel onSave={(b) => post("/revert", b)} onClose={() => setPanel(null)} />}
      {panel === "deadline" && <ChangeDeadlinePanel t={t} onSave={(b) => post("/deadline", b)} onClose={() => setPanel(null)} />}
      {panel === "extension" && <RequestExtensionPanel t={t} onSave={(b) => post("/extension-requests", b)} onClose={() => setPanel(null)} />}
      {panel === "explain" && <ExplainPanel t={t} onSubmit={(b) => post("/delay-reasons", b)} onClose={() => setPanel(null)} error={act.error} busy={act.isPending} />}
      {panel === "blocker" && <RaiseBlockerPanel onSave={(b) => act.mutate({ path: "/blockers", body: b })} onClose={() => setPanel(null)} error={act.error} busy={act.isPending} />}
      {panel === "review_delay" && <ReviewDelayPanel onSave={(b) => reviewDelay.mutate(b)} onClose={() => setPanel(null)} />}

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-5">
          <Card className="p-5">
            <h2 className="text-sm font-semibold">Description</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{t.description}</p>
            {t.instructions && (<><h2 className="mt-5 text-sm font-semibold">Special Note</h2><p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{t.instructions}</p></>)}
            {t.status === "cancelled" && <p className="mt-4 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700"><b>Cancelled:</b> {t.cancel_reason}</p>}
            <div className="mt-5">
              <div className="flex justify-between text-xs text-slate-500"><span>Progress</span><span>{t.progress_pct}%</span></div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-indigo-500" style={{ width: `${t.progress_pct}%` }} /></div>
            </div>
          </Card>

          {(t.assurances?.length ?? 0) > 0 && (
            <Card className="p-5">
              <h2 className="text-sm font-semibold">Completion</h2>
              <ul className="mt-3 space-y-4 text-sm">
                {t.assurances!.map((a) => (
                  <li key={a.attempt} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center justify-between"><b>Attempt {a.attempt}</b><span className="text-xs text-slate-500">{fmtDateTime(a.at, tz)}</span></div>
                    <p className="mt-1 text-slate-700">{a.summary}</p>
                    <p className="mt-1 text-xs text-slate-500">{a.tested ? "Tested by the assignee" : "Not tested"}{a.test_notes ? ` — ${a.test_notes}` : ""}{a.no_time_reason ? ` · No time tracked: ${a.no_time_reason}` : ""}</p>
                    {a.evidence_url && <a href={a.evidence_url} target="_blank" rel="noreferrer noopener" className="mt-1 inline-block text-xs text-indigo-600 hover:underline">Evidence link</a>}
                    {t.reverts?.filter((r) => r.attempt === a.attempt).map((r, i) => (
                      <div key={i} className="mt-2 rounded bg-orange-50 px-2 py-1.5 text-xs text-orange-900">
                        <p><b>Sent back</b> ({r.reason_code.replace("_", " ")}{r.found_by ? `, found by ${r.found_by}` : ""}): {r.reason}</p>
                        {r.bug_sheet_url && (
                          <p className="mt-1">
                            <a href={r.bug_sheet_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-indigo-700 underline hover:text-indigo-900">
                              🔗 Open Bug Sheet / Excel
                            </a>
                          </p>
                        )}
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {(t.updates?.length ?? 0) > 0 && (
            <Card className="p-5">
              <h2 className="text-sm font-semibold">Progress updates</h2>
              <ul className="mt-3 divide-y divide-slate-100 text-sm">
                {t.updates!.map((u, i) => <li key={i} className="py-2"><b>{u.progress_pct}%</b> · {u.note} <span className="text-xs text-slate-400">· {fmtDateTime(u.at, tz)}</span></li>)}
              </ul>
            </Card>
          )}

          <BlockersSection blockers={t.blockers ?? []} tz={tz} onChanged={refresh} />

          <DelaySection t={t} tz={tz} canReview={can("review_delay")} onReview={() => setPanel("review_delay")} />

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Files</h2>
              <>
                <input ref={fileRef} type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
                <Button variant="outline" disabled={upload.isPending} onClick={() => fileRef.current?.click()}>{upload.isPending ? "Uploading…" : "Attach file"}</Button>
              </>
            </div>
            <ul className="mt-3 divide-y divide-slate-100 text-sm">
              {t.attachments?.length === 0 && <li className="py-2 text-slate-500">No files attached.</li>}
              {t.attachments?.map((a) => (
                <li key={a.id} className="flex items-center justify-between py-2">
                  <span>{a.name} <span className="text-xs text-slate-400">· {(a.size_bytes / 1024).toFixed(1)} KB · {fmtDay(a.at, tz)}</span></span>
                  <Button variant="ghost" onClick={() => apiDownload(`/attachments/${a.id}/download`, a.name)}>Download</Button>
                </li>
              ))}
            </ul>
          </Card>

          <Discussion taskId={t.id} tz={tz} myUserId={me?.user.id} />

          <Card className="p-5">
            <h2 className="text-sm font-semibold">Activity</h2>
            <p className="text-xs text-slate-500">Everything that happens to this task is recorded here.</p>
            <ol className="mt-4 space-y-4 border-l border-slate-200 pl-4">
              {timeline.data?.map((e) => (
                <li key={e.id} className="relative">
                  <span className="absolute -left-[1.4rem] top-1.5 h-2.5 w-2.5 rounded-full bg-indigo-500" />
                  <div className="text-sm font-medium">{ACTION_LABEL[e.action] ?? e.action}</div>
                  {describe(e, names) && <div className="text-sm text-slate-600">{describe(e, names)}</div>}
                  <div className="text-xs text-slate-400">{e.actor ?? "System"} · {fmtDateTime(e.at, tz)}</div>
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <div className="space-y-5">
          <Card className="p-4 text-sm">
            <h2 className="text-sm font-semibold">People & Assignment</h2>
            <dl className="mt-3 space-y-3">
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Created By</dt>
                <dd className="font-medium text-slate-900">{t.assigned_by.full_name}</dd>
                <dd className="text-xs text-slate-500">{t.assigned_by.job_title ?? "—"}</dd>
              </div>

              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Assigned To</dt>
                <dd className="font-medium text-slate-900">{t.assignee.full_name}</dd>
                <dd className="text-xs text-slate-500">{t.assignee.job_title ?? "—"}</dd>
              </div>

              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Responsible Head</dt>
                {t.heads && t.heads.length > 0 ? (
                  <div className="space-y-1">
                    {t.heads.map((h, i) => (
                      <dd key={h.id} className="font-medium text-slate-900">
                        {h.full_name} <span className="text-xs font-normal text-slate-500">({i === 0 ? "Head" : "SubHead / Head"}{h.job_title ? ` · ${h.job_title}` : ""})</span>
                      </dd>
                    ))}
                  </div>
                ) : t.head ? (
                  <dd className="font-medium text-slate-900">
                    {t.head.full_name} <span className="text-xs font-normal text-slate-500">(Head{t.head.job_title ? ` · ${t.head.job_title}` : ""})</span>
                  </dd>
                ) : t.sub_head ? (
                  <dd className="font-medium text-slate-900">
                    {t.sub_head.full_name} <span className="text-xs font-normal text-slate-500">(SubHead{t.sub_head.job_title ? ` · ${t.sub_head.job_title}` : ""})</span>
                  </dd>
                ) : (
                  <dd className="text-slate-500 italic">None (Specific Employee Task)</dd>
                )}
              </div>

              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Assigned QA</dt>
                {t.qa_members && t.qa_members.length > 0 ? (
                  <dd className="font-medium text-slate-900">
                    {t.qa_members.map((q) => q.full_name).join(", ")}
                  </dd>
                ) : t.qa ? (
                  <dd className="font-medium text-slate-900">{t.qa.full_name}</dd>
                ) : (
                  <dd className="text-slate-500 italic">No QA assigned</dd>
                )}
              </div>

              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Task Owner</dt>
                {t.ownership && t.ownership.length > 0 ? (
                  <div>
                    <dd className="font-medium text-indigo-700">{t.ownership[t.ownership.length - 1].full_name}</dd>
                    <dd className="text-xs text-slate-500">Ownership claimed by Department Leadership</dd>
                  </div>
                ) : (
                  <div>
                    <dd className="font-medium text-slate-900">{t.assignee.full_name}</dd>
                    <dd className="text-xs text-slate-500">Task Assignee (Default Owner)</dd>
                  </div>
                )}
              </div>

              {t.acknowledged_at && (
                <div className="border-t border-slate-100 pt-2">
                  <dt className="text-xs text-slate-500">Acknowledged</dt>
                  <dd className="text-xs text-slate-700">{fmtDateTime(t.acknowledged_at, tz)}</dd>
                </div>
              )}
            </dl>
          </Card>

          <Card className="p-4 text-sm">
            <h2 className="text-sm font-semibold text-slate-900">Transfer History</h2>
            <p className="text-xs text-slate-500 mb-3">Chronological assignment & transfer audit trail.</p>
            {t.assignment_history && t.assignment_history.length > 0 ? (
              <ol className="relative border-l border-slate-200 pl-4 space-y-3.5">
                {t.assignment_history.map((a, idx) => (
                  <li key={a.id} className="relative">
                    <span className="absolute -left-[1.35rem] top-1 h-2.5 w-2.5 rounded-full bg-indigo-500 ring-2 ring-white" />
                    <div className="text-xs font-semibold text-slate-800">
                      {idx === 0 ? "Initial Assignment" : "Task Transferred"}
                    </div>
                    <div className="text-xs text-slate-700 mt-0.5">
                      Assigned to <span className="font-medium text-slate-900">{a.assignee?.full_name ?? `#${a.id}`}</span>
                      {a.assigned_by ? <span> by <span className="font-medium text-slate-900">{a.assigned_by.full_name}</span></span> : null}
                    </div>
                    {a.reason && (
                      <p className="mt-1 rounded bg-slate-50 p-1.5 text-xs text-slate-600 italic border border-slate-100">
                        “{a.reason}”
                      </p>
                    )}
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      {fmtDateTime(a.assigned_at, tz)}
                      {a.unassigned_at ? ` · Handed over ${fmtDateTime(a.unassigned_at, tz)}` : " · Current"}
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-xs text-slate-500 italic">No transfer records found.</p>
            )}
          </Card>
          {t.deadline && (
            <DeadlineCard
              t={t} tz={tz} onChange={() => toggle("deadline")} onRequest={() => toggle("extension")}
              canChange={can("change_deadline")} canRequest={can("request_extension")} canDecide={can("change_deadline")}
            />
          )}
          <Card className="p-4 text-sm">
            <h2 className="text-sm font-semibold">Details</h2>
            <dl className="mt-3 space-y-3">
              {t.start_date && <div><dt className="text-xs text-slate-500">Start date</dt><dd>{t.start_date}</dd></div>}
              {t.project && <div><dt className="text-xs text-slate-500">Project</dt><dd>{t.project}</dd></div>}
              {t.category && <div><dt className="text-xs text-slate-500">Category</dt><dd>{t.category}</dd></div>}
              {t.type && <div><dt className="text-xs text-slate-500">Type</dt><dd>{t.type}</dd></div>}
              <div><dt className="text-xs text-slate-500">Status history</dt>
                <dd className="mt-1 space-y-1">{t.status_history?.map((h, i) => <div key={i} className="text-xs text-slate-600">{h.from ? statusLabel(h.from) : "—"} → {statusLabel(h.to)} <span className="text-slate-400">· {fmtDay(h.at, tz)}</span></div>)}</dd>
              </div>
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ action panels

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <Card className="mb-4 p-4"><h2 className="mb-3 text-sm font-semibold">{title}</h2>{children}</Card>;
}
const Buttons = ({ cta, onClose, danger, disabled }: { cta: string; onClose: () => void; danger?: boolean; disabled?: boolean }) => (
  <div className="flex items-end gap-2"><Button type="submit" variant={danger ? "danger" : "primary"} disabled={disabled}>{cta}</Button><Button type="button" variant="outline" onClick={onClose}>Cancel</Button></div>
);

function EditPanel({ t, onSave, onClose }: { t: Task; onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [f, setF] = useState({
    title: t.title,
    description: t.description ?? "",
    instructions: t.instructions ?? "",
  });
  const initialHeads = useMemo(() => {
    if (t.heads && t.heads.length > 0) return t.heads.map((h) => h.id);
    const arr: number[] = [];
    if (t.head) arr.push(t.head.id);
    if (t.sub_head) arr.push(t.sub_head.id);
    return arr;
  }, [t.head, t.sub_head, t.heads]);
  const [selectedHeads, setSelectedHeads] = useState<number[]>(initialHeads);
  const [headSearch, setHeadSearch] = useState("");
  const [qaSearch, setQaSearch] = useState("");

  const initialQAs = useMemo(() => {
    if (t.qa_members && t.qa_members.length > 0) return t.qa_members.map((q) => q.id);
    if (t.qa) return [t.qa.id];
    return [];
  }, [t.qa, t.qa_members]);
  const [selectedQAs, setSelectedQAs] = useState<number[]>(initialQAs);
  const emps = useEmployees();
  const filteredHeads = useMemo(
    () => (emps.data ?? []).filter((e) => e.id !== t.assignee.id && (e.full_name.toLowerCase().includes(headSearch.toLowerCase()) || (e.job_title ?? "").toLowerCase().includes(headSearch.toLowerCase()))),
    [emps.data, t.assignee.id, headSearch],
  );
  const filteredQAs = useMemo(
    () => (emps.data ?? []).filter((e) => e.id !== t.assignee.id && (e.full_name.toLowerCase().includes(qaSearch.toLowerCase()) || (e.job_title ?? "").toLowerCase().includes(qaSearch.toLowerCase()))),
    [emps.data, t.assignee.id, qaSearch],
  );

  const toggleHead = (id: number) => {
    setSelectedHeads((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };
  const toggleQA = (id: number) => {
    setSelectedQAs((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  return (
    <Panel title="Edit task (the deadline is changed separately, with a reason)">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave({
            title: f.title,
            description: f.description,
            instructions: f.instructions || null,
            head_employee_id: selectedHeads[0] ?? null,
            sub_head_employee_id: selectedHeads[1] ?? null,
            head_employee_ids: selectedHeads,
            qa_employee_id: selectedQAs[0] ?? null,
            qa_employee_ids: selectedQAs,
          });
        }}
        className="grid gap-3 sm:grid-cols-2"
      >
        <div className="sm:col-span-2"><Field label="Title"><Input required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field></div>
        <div className="sm:col-span-2"><Field label="Description"><textarea required rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} className={textarea} /></Field></div>
        <div className="sm:col-span-2"><Field label="Special Note"><textarea rows={2} value={f.instructions} onChange={(e) => setF({ ...f, instructions: e.target.value })} className={textarea} placeholder="Special note..." /></Field></div>

        <div className="sm:col-span-2">
          <Field label={`Responsible Heads (${selectedHeads.length} selected, multiple heads supported)`}>
            <div className="space-y-1.5">
              <Input
                placeholder="Search heads..."
                value={headSearch}
                onChange={(e) => setHeadSearch(e.target.value)}
                className="text-xs py-1"
              />
              <div className="max-h-36 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1">
                {filteredHeads.map((e) => (
                  <label key={e.id} className="flex items-center gap-2 text-xs text-slate-700 hover:bg-slate-50 p-1 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedHeads.includes(e.id)}
                      onChange={() => toggleHead(e.id)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>{e.full_name}{e.job_title ? ` · ${e.job_title}` : ""}</span>
                  </label>
                ))}
                {filteredHeads.length === 0 && <p className="p-1 text-xs text-slate-400">No matching heads.</p>}
              </div>
            </div>
          </Field>
        </div>

        <div className="sm:col-span-2">
          <Field label={`QA Testers (${selectedQAs.length} selected, multiple QA members share one testing status)`}>
            <div className="space-y-1.5">
              <Input
                placeholder="Search QA members..."
                value={qaSearch}
                onChange={(e) => setQaSearch(e.target.value)}
                className="text-xs py-1"
              />
              <div className="max-h-36 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1">
                {filteredQAs.map((e) => (
                  <label key={e.id} className="flex items-center gap-2 text-xs text-slate-700 hover:bg-slate-50 p-1 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedQAs.includes(e.id)}
                      onChange={() => toggleQA(e.id)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>{e.full_name}{e.job_title ? ` · ${e.job_title}` : ""}</span>
                  </label>
                ))}
                {filteredQAs.length === 0 && <p className="p-1 text-xs text-slate-400">No matching QA testers.</p>}
              </div>
            </div>
          </Field>
        </div>
        <Buttons cta="Save" onClose={onClose} />
      </form>
    </Panel>
  );
}

function ReassignPanel({ t, people, onSave, onClose }: { t: Task; people: Workload[]; onSave: (b: { assignee_id: number; reason: string | null }) => void; onClose: () => void }) {
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const options = people.filter((p) => p.employee_id !== t.assignee.id && !p.is_me);
  return (
    <Panel title="Transfer task to another employee">
      <form onSubmit={(e) => { e.preventDefault(); onSave({ assignee_id: Number(to), reason: reason || null }); }} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
        <Field label="Transfer to">
          <Select required value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="">Select employee…</option>
            {options.map((p) => <option key={p.employee_id} value={p.employee_id}>{p.full_name} — {p.open_tasks} open{p.overdue_tasks ? `, ${p.overdue_tasks} overdue` : ""}</option>)}
          </Select>
        </Field>
        <Field label="Transfer reason (required for audit trail)"><Input required minLength={3} placeholder="Reason for transfer" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <Buttons cta="Transfer task" onClose={onClose} />
      </form>
    </Panel>
  );
}

function PriorityPanel({ t, onSave, onClose }: { t: Task; onSave: (b: { priority: string; reason: string | null }) => void; onClose: () => void }) {
  const [p, setP] = useState(t.priority);
  const [reason, setReason] = useState("");
  return (
    <Panel title="Change priority">
      <form onSubmit={(e) => { e.preventDefault(); onSave({ priority: p, reason: reason || null }); }} className="grid gap-3 sm:grid-cols-[12rem_1fr_auto]">
        <Field label="Priority"><Select value={p} onChange={(e) => setP(e.target.value)}>{["critical", "high", "medium", "low"].map((x) => <option key={x} value={x}>{x[0].toUpperCase() + x.slice(1)}</option>)}</Select></Field>
        <Field label="Reason (optional)"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <Buttons cta="Save" onClose={onClose} disabled={p === t.priority} />
      </form>
    </Panel>
  );
}

function ReasonPanel({ title, label, cta, danger, onSave, onClose }: { title: string; label: string; cta: string; danger?: boolean; onSave: (r: string) => void; onClose: () => void }) {
  const [reason, setReason] = useState("");
  return (
    <Panel title={title}>
      <form onSubmit={(e) => { e.preventDefault(); onSave(reason); }} className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <Field label={label}><Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <Buttons cta={cta} danger={danger} onClose={onClose} />
      </form>
    </Panel>
  );
}

function ProgressPanel({ t, onSave, onClose }: { t: Task; onSave: (b: { progress_pct: number; note: string }) => void; onClose: () => void }) {
  const [pct, setPct] = useState(t.progress_pct);
  const [note, setNote] = useState("");
  return (
    <Panel title="Update progress">
      <form onSubmit={(e) => { e.preventDefault(); onSave({ progress_pct: pct, note }); }} className="grid gap-3 sm:grid-cols-[14rem_1fr_auto]">
        <Field label={`Progress: ${pct}%`}><input type="range" min={0} max={100} step={5} value={pct} onChange={(e) => setPct(Number(e.target.value))} className="w-full" /></Field>
        <Field label="What was done?"><Input required minLength={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <Buttons cta="Save update" onClose={onClose} />
      </form>
    </Panel>
  );
}

function FinishPanel({ t, review, lateRequired, onSave, onClose }: { t: Task; review: boolean; lateRequired: boolean; onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [summary, setSummary] = useState("");
  const [tested, setTested] = useState(true);
  const [notes, setNotes] = useState("");
  const [evidence, setEvidence] = useState("");
  const [late, setLate] = useState("");
  return (
    <Panel title={review ? "Submit for review" : "Mark as complete"}>
      <p className="mb-3 text-xs text-slate-500">
        {t.project_id || t.head || t.qa ? `The QA (if there is one) tests it first and sends bugs back to you to fix, then the head (if there is one) approves it, then the CEO or Owner reviews it. It counts as completed only after that.` : review ? "A reviewer will check this before it counts as completed." : "You are confirming the work is done. A manager can still verify it, or send it back if a problem turns up later."}
      </p>
      <form
        onSubmit={(e) => { e.preventDefault(); onSave({ summary, tested, test_notes: notes || null, evidence_url: evidence || null, late_reason: late.trim() || null }); }}
        className="grid gap-3 sm:grid-cols-2"
      >
        <div className="sm:col-span-2"><Field label="What did you do?"><textarea required minLength={5} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} className={textarea} /></Field></div>
        <fieldset className="sm:col-span-2 flex flex-wrap items-center gap-4 text-sm">
          <legend className="mb-1 text-xs font-medium text-slate-600">I have tested this</legend>
          <label className="flex items-center gap-2"><input type="radio" checked={tested} onChange={() => setTested(true)} /> Yes, it works as required</label>
          <label className="flex items-center gap-2"><input type="radio" checked={!tested} onChange={() => setTested(false)} /> No / not fully</label>
        </fieldset>
        <div className="sm:col-span-2"><Field label={tested ? "Test notes (optional)" : "Why not, or what remains to be tested? (required)"}><Input required={!tested} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field></div>
        <Field label="Evidence link (optional: pull request, test run, demo)"><Input type="url" placeholder="https://" value={evidence} onChange={(e) => setEvidence(e.target.value)} /></Field>
        {(t.delay?.required || lateRequired) && (
          <div className="sm:col-span-2 rounded-lg border border-red-200 bg-red-50 p-3">
            <Field label="This task is past its deadline. Why was it late? (required)">
              <textarea required minLength={5} rows={3} autoFocus value={late} onChange={(e) => setLate(e.target.value)} placeholder="e.g. The client changed the design twice, so the work took longer." className={textarea} />
            </Field>
          </div>
        )}
        <div className="sm:col-span-2"><Buttons cta={review ? "Submit for review" : "Mark complete"} onClose={onClose} /></div>
      </form>
    </Panel>
  );
}

function SubmitToOwnerPanel({ onSave, onClose }: { onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [summary, setSummary] = useState("");
  const [tested, setTested] = useState(true);
  const [notes, setNotes] = useState("");
  const [evidence, setEvidence] = useState("");

  return (
    <Panel title="Complete & Submit to Owner">
      <p className="mb-3 text-xs text-slate-500">
        As CEO, you can complete this task directly and submit it to the Owner for executive review, as an allowed alternative to transferring it onward.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave({ summary, tested, test_notes: notes || null, evidence_url: evidence || null });
        }}
        className="grid gap-3 sm:grid-cols-2"
      >
        <div className="sm:col-span-2">
          <Field label="What was completed? (Summary)">
            <textarea required minLength={5} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} className={textarea} placeholder="Summary of work completed..." />
          </Field>
        </div>
        <fieldset className="sm:col-span-2 flex flex-wrap items-center gap-4 text-sm">
          <legend className="mb-1 text-xs font-medium text-slate-600">Verification status</legend>
          <label className="flex items-center gap-2"><input type="radio" checked={tested} onChange={() => setTested(true)} /> Tested & verified</label>
          <label className="flex items-center gap-2"><input type="radio" checked={!tested} onChange={() => setTested(false)} /> Not fully tested</label>
        </fieldset>
        {!tested && (
          <div className="sm:col-span-2">
            <Field label="Notes on remaining testing (required)">
              <Input required value={notes} onChange={(e) => setNotes(e.target.value)} />
            </Field>
          </div>
        )}
        <Field label="Evidence link (optional)"><Input type="url" placeholder="https://" value={evidence} onChange={(e) => setEvidence(e.target.value)} /></Field>
        <div className="sm:col-span-2">
          <Buttons cta="Complete & Submit to Owner" onClose={onClose} />
        </div>
      </form>
    </Panel>
  );
}

function ReviewPanel({ stage, onSave, onClose }: { stage: "qa" | "head" | "leadership" | null; onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [decision, setDecision] = useState<"approve" | "reject">("approve");
  const [code, setCode] = useState(stage === "qa" ? "qa_defect" : "incomplete");
  const [comment, setComment] = useState("");
  const [bugSheetUrl, setBugSheetUrl] = useState("");
  const [solved, setSolved] = useState(false);
  return (
    <Panel title={stage === "qa" ? "Test this work (QA)" : stage === "head" ? "Approve this work (head)" : stage === "leadership" ? "Review this work (CEO / Owner)" : "Review submitted work"}>
      {stage === "qa" && <p className="mb-3 text-xs text-slate-500">Found a bug? Choose “Report bugs” and describe them: the task goes back to the developer, who fixes them and submits it again for you to re-test. When everything works and every bug is solved, tick the box and pass it to the head.</p>}
      {stage === "head" && <p className="mb-3 text-xs text-slate-500">If you approve, it goes to the CEO or Owner for the final review. You can also send it back.</p>}
      {stage === "leadership" && <p className="mb-3 text-xs text-slate-500">Marking it reviewed completes the task. Either the CEO or the Owner can do this.</p>}
      <form onSubmit={(e) => { e.preventDefault(); onSave({ decision, reason_code: decision === "reject" ? code : null, comment: comment || null, bug_sheet_url: (decision === "reject" && bugSheetUrl.trim()) ? bugSheetUrl.trim() : null }); }} className="grid gap-3 sm:grid-cols-2">
        <Field label="Decision"><Select value={decision} onChange={(e) => setDecision(e.target.value as "approve" | "reject")}><option value="approve">{stage === "qa" ? "Passed: all bugs solved, send to the head" : stage === "head" ? "Approve: send to CEO / Owner" : stage === "leadership" ? "Reviewed: mark completed" : "Approve: it is done"}</option><option value="reject">{stage === "qa" ? "Report bugs: send back to the developer" : "Send back for changes"}</option></Select></Field>
        {decision === "reject" && <Field label="Reason"><Select value={code} onChange={(e) => setCode(e.target.value)}>{REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>}
        <div className="sm:col-span-2"><Field label={decision === "reject" ? (stage === "qa" ? "Describe the bugs you found (required)" : "What needs to change? (required)") : "Comment (optional)"}><Input required={decision === "reject"} value={comment} onChange={(e) => setComment(e.target.value)} /></Field></div>
        {decision === "reject" && (
          <div className="sm:col-span-2">
            <Field label="Bug sheet / Google Sheet link (optional)">
              <Input type="url" placeholder="https://docs.google.com/spreadsheets/d/..." value={bugSheetUrl} onChange={(e) => setBugSheetUrl(e.target.value)} />
            </Field>
          </div>
        )}
        {stage === "qa" && decision === "approve" && <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={solved} onChange={(e) => setSolved(e.target.checked)} /> I tested it and every bug is solved</label>}
        <Buttons cta={decision === "approve" ? (stage === "leadership" ? "Mark reviewed" : stage === "qa" ? "Pass QA" : "Approve") : stage === "qa" ? "Report bugs" : "Send back"} danger={decision === "reject"} disabled={stage === "qa" && decision === "approve" && !solved} onClose={onClose} />
      </form>
    </Panel>
  );
}

function RevertPanel({ onSave, onClose }: { onSave: (b: Record<string, unknown>) => void; onClose: () => void }) {
  const [code, setCode] = useState("qa_defect");
  const [reason, setReason] = useState("");
  const [foundBy, setFoundBy] = useState("QA");
  const [bugSheetUrl, setBugSheetUrl] = useState("");
  return (
    <Panel title="Revert: send this completed work back">
      <p className="mb-3 text-xs text-slate-500">The task returns to the assignee as <b>Reopened</b>. The original completion stays in the record and the rework is counted.</p>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ reason_code: code, reason, found_by: foundBy || null, bug_sheet_url: bugSheetUrl.trim() || null }); }} className="grid gap-3 sm:grid-cols-2">
        <Field label="Reason"><Select value={code} onChange={(e) => setCode(e.target.value)}>{REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
        <Field label="Found by (optional)"><Input value={foundBy} onChange={(e) => setFoundBy(e.target.value)} placeholder="e.g. QA" /></Field>
        <div className="sm:col-span-2"><Field label="What is wrong? (the assignee will read this)"><textarea required minLength={5} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} className={textarea} /></Field></div>
        <div className="sm:col-span-2">
          <Field label="Bug sheet / Google Sheet link (optional)">
            <Input type="url" placeholder="https://docs.google.com/spreadsheets/d/..." value={bugSheetUrl} onChange={(e) => setBugSheetUrl(e.target.value)} />
          </Field>
        </div>
        <Buttons cta="Revert task" danger onClose={onClose} />
      </form>
    </Panel>
  );
}
