import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button, Card, ErrorNote, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Role = { id: number; code: string; name: string; rank: number; permissions: Record<string, string> };
type Perm = { code: string; category: string | null; description: string | null };
type Draft = Record<number, Record<string, string>>; // roleId -> permission -> scope ("" = none)

const SCOPES = ["", "self", "team", "department", "organization"];
const LABEL: Record<string, string> = { "": "—", self: "Self", team: "Team", department: "Department", organization: "Organization" };

export function Roles() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api<Perm[]>("/permissions") });
  const [draft, setDraft] = useState<Draft>({});
  const [saved, setSaved] = useState<number | null>(null);

  useEffect(() => {
    if (roles.data) setDraft(Object.fromEntries(roles.data.map((r) => [r.id, { ...r.permissions }])));
  }, [roles.data]);

  const save = useMutation({
    mutationFn: (role: Role) => {
      const grants = Object.entries(draft[role.id] ?? {}).filter(([, s]) => s).map(([permission, scope]) => ({ permission, scope }));
      return api(`/roles/${role.id}/permissions`, { method: "PUT", body: { grants } });
    },
    onSuccess: (_d, role) => {
      setSaved(role.id);
      qc.invalidateQueries({ queryKey: ["roles"] });
    },
  });

  if (roles.isLoading || perms.isLoading) return <Spinner />;
  const dirty = (r: Role) => JSON.stringify(sorted(draft[r.id] ?? {})) !== JSON.stringify(sorted(r.permissions));
  const sorted = (o: Record<string, string>) => Object.entries(o).filter(([, s]) => s).sort();

  return (
    <>
      <PageHeader title="Roles & permissions" subtitle="Each permission is granted with a scope: self, team, department or organization. Changes apply on the next request and are audited." />
      <Card className="overflow-x-auto">
        <table data-no-stack className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs text-slate-500">
            <tr>
              <th className="p-3">Permission</th>
              {roles.data?.map((r) => (
                <th key={r.id} className="p-3">
                  {r.name}
                  <div className="font-normal text-slate-400">rank {r.rank}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {perms.data?.map((p) => (
              <tr key={p.code} className="border-b border-slate-100 last:border-0">
                <td className="p-3">
                  <div className="font-medium">{p.code}</div>
                  <div className="text-xs text-slate-500">{p.description}</div>
                </td>
                {roles.data?.map((r) => (
                  <td key={r.id} className="p-2">
                    <Select
                      aria-label={`${r.name}: ${p.code}`}
                      disabled={r.rank > (me?.rank ?? 0)}
                      className="min-w-32 py-1.5 text-xs"
                      value={draft[r.id]?.[p.code] ?? ""}
                      onChange={(e) => {
                        setSaved(null);
                        setDraft({ ...draft, [r.id]: { ...draft[r.id], [p.code]: e.target.value } });
                      }}
                    >
                      {SCOPES.map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}
                    </Select>
                  </td>
                ))}
              </tr>
            ))}
            <tr className="bg-slate-50">
              <td className="p-3 text-xs text-slate-500">Save changes per role</td>
              {roles.data?.map((r) => (
                <td key={r.id} className="p-2">
                  <Button className="w-full py-1.5 text-xs" disabled={!dirty(r) || save.isPending} onClick={() => save.mutate(r)}>
                    {saved === r.id ? "Saved ✓" : "Save"}
                  </Button>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </Card>
      <div className="mt-3"><ErrorNote error={save.error} /></div>
    </>
  );
}
