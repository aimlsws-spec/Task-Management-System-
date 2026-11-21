import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ArrowRight, Briefcase, Building2, CheckCircle2, LogOut, Sparkles } from "lucide-react";
import { AuthLayout } from "@/components/AuthLayout";
import { Button, ErrorNote, Input, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Dept = { id: number; name: string; is_active: boolean; is_system: boolean; self_service: boolean };

const POPULAR_DESIGNATIONS = [
  "Frontend Developer",
  "Backend Developer",
  "Full Stack Developer",
  "QA Engineer",
  "UI/UX Designer",
  "AI/ML Engineer",
  "DevOps Engineer",
  "Project Coordinator",
];

export function Onboarding() {
  const { me, reload, logout } = useAuth();
  const depts = useQuery({ queryKey: ["departments"], queryFn: () => api<Dept[]>("/departments") });
  const [dept, setDept] = useState("");
  const [designation, setDesignation] = useState("");

  const save = useMutation({
    mutationFn: () => api("/me/onboarding", { body: { department_id: Number(dept), designation } }),
    onSuccess: () => reload(),
  });

  const options = depts.data?.filter((d) => d.is_active && d.self_service && !d.is_system) ?? [];
  const selectedDeptObj = options.find((d) => String(d.id) === dept);
  const firstName = me?.employee ? me.employee.full_name.split(" ")[0] : "";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!dept || !designation.trim()) return;
    save.mutate();
  };

  return (
    <AuthLayout
      title={`Welcome${firstName ? `, ${firstName}` : ""}!`}
      subtitle="Complete your profile to set up your workspace."
    >
      {depts.isLoading ? (
        <div className="flex flex-col items-center justify-center py-10">
          <Spinner />
          <p className="mt-3 text-xs text-slate-500">Loading department information…</p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-5">
          {/* Progress / Step pill */}
          <div className="flex items-center gap-2 rounded-lg bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700">
            <Sparkles className="h-4 w-4 shrink-0 text-indigo-600" />
            <span>Step 2 of 2: Set up your role & department</span>
          </div>

          {options.length === 0 ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-semibold">No departments available yet</p>
              <p className="mt-1 text-xs text-amber-800">
                Your organization administrator has not created any department yet. Please ask your administrator to add your department in the Admin panel, then refresh this page.
              </p>
              <div className="mt-3 flex gap-2">
                <Button type="button" variant="outline" onClick={() => depts.refetch()} className="text-xs">
                  Refresh
                </Button>
                <button type="button" onClick={logout} className="text-xs text-slate-600 underline">
                  Sign out
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Department field */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="onboarding-dept" className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                    <Building2 className="h-3.5 w-3.5 text-indigo-600" />
                    Department <span className="text-rose-500">*</span>
                  </label>
                  {selectedDeptObj && (
                    <span className="text-[11px] font-medium text-emerald-600">Selected</span>
                  )}
                </div>
                <Select
                  id="onboarding-dept"
                  required
                  value={dept}
                  onChange={(e) => setDept(e.target.value)}
                  className="w-full"
                >
                  <option value="">Select your department…</option>
                  {options.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </Select>
                <p className="text-[11px] text-slate-500">
                  Tasks, team members, and department heads are organized by department.
                </p>
              </div>

              {/* Designation field */}
              <div className="space-y-1.5">
                <label htmlFor="onboarding-designation" className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                  <Briefcase className="h-3.5 w-3.5 text-indigo-600" />
                  Designation / Job Title <span className="text-rose-500">*</span>
                </label>
                <Input
                  id="onboarding-designation"
                  required
                  minLength={2}
                  maxLength={100}
                  value={designation}
                  onChange={(e) => setDesignation(e.target.value)}
                  placeholder="e.g. Senior Frontend Developer"
                  className="w-full"
                />
                <p className="text-[11px] text-slate-500">
                  Your official job title shown to team members on tasks.
                </p>

                {/* Quick suggestion chips */}
                <div className="pt-1">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                    Quick suggestions:
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {POPULAR_DESIGNATIONS.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => setDesignation(item)}
                        className={`rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
                          designation === item
                            ? "border-indigo-600 bg-indigo-50 font-semibold text-indigo-700 ring-1 ring-indigo-600"
                            : "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-slate-100"
                        }`}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Summary benefit card */}
              <div className="rounded-xl border border-slate-100 bg-slate-50/80 p-3 text-xs text-slate-600 space-y-1.5">
                <div className="flex items-center gap-1.5 text-emerald-700 font-medium">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  What happens next:
                </div>
                <ul className="list-disc pl-4 text-[11px] text-slate-500 space-y-0.5">
                  <li>You will be placed under your department head</li>
                  <li>Direct access to your tasks, time logging, and personal dashboard</li>
                </ul>
              </div>

              <ErrorNote error={save.error} />

              <Button
                type="submit"
                className="w-full py-2.5 font-medium shadow-sm"
                disabled={save.isPending || !dept || !designation.trim()}
              >
                {save.isPending ? "Setting up profile…" : (
                  <span className="flex items-center justify-center gap-1.5">
                    Enter Dashboard <ArrowRight className="h-4 w-4" />
                  </span>
                )}
              </Button>

              <button
                type="button"
                onClick={logout}
                className="flex items-center justify-center gap-1.5 w-full text-center text-xs text-slate-400 hover:text-slate-600 transition-colors pt-1"
              >
                <LogOut className="h-3.5 w-3.5" /> Sign out
              </button>
            </>
          )}
        </form>
      )}
    </AuthLayout>
  );
}
