import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  GitFork,
  Layers,
  Network,
  Search,
  UserPlus,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type HierarchyNode = {
  id: number;
  full_name: string;
  employee_code?: string;
  job_title: string | null;
  department_id: number;
  department_name?: string;
  email?: string;
  company_id: number;
  reports_to_id: number | null;
  roles?: string[];
  children: HierarchyNode[];
};

type Company = {
  id: number;
  name: string;
  code: string;
  logo_url?: string | null;
  is_active: boolean;
};

type EmployeeItem = {
  id: number;
  full_name: string;
  employee_code: string;
  email: string;
  job_title: string | null;
  department_id: number;
  company_id: number;
  status: string;
  is_active: boolean;
  reports_to_id: number | null;
  roles: string[];
};

function initials(name?: string | null) {
  const parts = (name ?? "?").split(/[\s@.]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[1][0] : "")).toUpperCase();
}

/** Collect all employee IDs in the subtree under `nodeId` (including `nodeId` itself) to prevent cycles */
function getSubtreeIds(nodes: HierarchyNode[], targetId: number): Set<number> {
  const result = new Set<number>();
  function findAndCollect(list: HierarchyNode[]): boolean {
    for (const node of list) {
      if (node.id === targetId) {
        collectAll(node);
        return true;
      }
      if (node.children && findAndCollect(node.children)) {
        return true;
      }
    }
    return false;
  }
  function collectAll(n: HierarchyNode) {
    result.add(n.id);
    for (const child of n.children || []) {
      collectAll(child);
    }
  }
  findAndCollect(nodes);
  return result;
}

export function Hierarchy() {
  const { me, can } = useAuth();
  const qc = useQueryClient();
  const isOwner = Boolean(me?.roles?.includes("owner"));
  const isCEO = Boolean(me?.roles?.includes("ceo"));

  const [activeTab, setActiveTab] = useState<"tree" | "table">("tree");
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>("");
  const [search, setSearch] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [editingEmployee, setEditingEmployee] = useState<{ id: number; full_name: string; current_manager_id: number | null } | null>(null);

  // Load companies caller is authorized to view
  const companiesQuery = useQuery({
    queryKey: ["companies"],
    queryFn: () => api<Company[]>("/companies"),
  });

  const companies = companiesQuery.data || [];

  // Determine effective company ID
  const effectiveCompanyId = useMemo(() => {
    if (selectedCompanyId) return selectedCompanyId;
    if (companies.length > 0) return String(companies[0].id);
    return "";
  }, [selectedCompanyId, companies]);

  const cidNum = effectiveCompanyId ? Number(effectiveCompanyId) : undefined;

  // Load tree
  const treeQuery = useQuery({
    queryKey: ["hierarchy-tree", cidNum],
    queryFn: () => api<HierarchyNode[]>("/hierarchy/tree", { params: cidNum ? { company_id: cidNum } : undefined }),
    enabled: !!cidNum || companies.length === 0,
  });

  // Load employees for company
  const employeesQuery = useQuery({
    queryKey: ["employees", "company", cidNum],
    queryFn: () =>
      api<{ items: EmployeeItem[]; total: number }>("/employees", {
        params: { company_id: cidNum, page_size: 200, status: "active" },
      }),
    enabled: !!cidNum || companies.length === 0,
  });

  const allEmployees = employeesQuery.data?.items || [];
  const rawTree = treeQuery.data || [];

  // Map employee ID -> Manager Name for quick table lookups
  const empMap = useMemo(() => {
    const map = new Map<number, EmployeeItem>();
    for (const e of allEmployees) {
      map.set(e.id, e);
    }
    return map;
  }, [allEmployees]);

  // Expand all / Collapse all helper
  const handleToggleExpandAll = () => {
    if (expandedIds.size > 0) {
      setExpandedIds(new Set());
    } else {
      const allIds = new Set<number>();
      function addAll(nodes: HierarchyNode[]) {
        for (const n of nodes) {
          allIds.add(n.id);
          if (n.children) addAll(n.children);
        }
      }
      addAll(rawTree);
      setExpandedIds(allIds);
    }
  };

  const toggleNode = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const currentCompany = companies.find((c) => String(c.id) === effectiveCompanyId);

  return (
    <>
      <PageHeader
        title="Employee Hierarchy & Reporting"
        subtitle={
          isCEO && !isOwner
            ? "Manage reporting relationships and executive hierarchy strictly for your authorized companies."
            : "Manage company reporting relationships, organizational structure, and manager assignments."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {can("employee.manage") && (
              <Link
                to="/role-emails"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 transition-colors"
              >
                <UserPlus size={16} /> Invite Employee
              </Link>
            )}
          </div>
        }
      />

      {/* Company Selector and View Controls */}
      <Card className="mb-6 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {companies.length > 1 && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Company:</span>
                <Select
                  value={effectiveCompanyId}
                  onChange={(e) => setSelectedCompanyId(e.target.value)}
                  className="w-56 font-medium text-slate-800"
                >
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code.toUpperCase()})
                    </option>
                  ))}
                </Select>
              </div>
            )}
            {currentCompany && (
              <Badge tone="indigo">
                {currentCompany.name}
              </Badge>
            )}
            <span className="text-xs text-slate-400">|</span>
            <div className="text-xs text-slate-600 font-medium">
              Total Employees: <strong className="text-slate-900">{allEmployees.length}</strong>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* View switcher */}
            <div className="inline-flex rounded-lg bg-slate-100 p-1 border border-slate-200">
              <button
                type="button"
                onClick={() => setActiveTab("tree")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                  activeTab === "tree" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Network size={14} /> Org Chart
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("table")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                  activeTab === "table" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Layers size={14} /> Reporting Lines Table
              </button>
            </div>

            {activeTab === "tree" && rawTree.length > 0 && (
              <Button variant="outline" className="text-xs py-1.5 px-3" onClick={handleToggleExpandAll}>
                {expandedIds.size > 0 ? "Collapse All" : "Expand All"}
              </Button>
            )}

            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <Input
                placeholder="Search person or title..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-48 pl-8 text-xs py-1.5"
              />
            </div>
          </div>
        </div>
      </Card>

      {/* Main Content Area */}
      {treeQuery.isLoading || companiesQuery.isLoading ? (
        <Card className="p-12 flex justify-center items-center">
          <Spinner />
        </Card>
      ) : rawTree.length === 0 ? (
        <Card className="p-8">
          <EmptyState
            icon={<GitFork size={28} className="text-slate-400" />}
            title="No hierarchy defined for this company"
            hint="Invite employees or add reporting relationships to visualize and manage the organization structure."
          />
        </Card>
      ) : activeTab === "tree" ? (
        <div className="space-y-4">
          {rawTree.map((rootNode) => (
            <TreeNodeItem
              key={rootNode.id}
              node={rootNode}
              expandedIds={expandedIds}
              onToggle={toggleNode}
              searchQuery={search}
              onEditManager={(node) =>
                setEditingEmployee({
                  id: node.id,
                  full_name: node.full_name,
                  current_manager_id: node.reports_to_id,
                })
              }
            />
          ))}
        </div>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50/75 text-xs uppercase tracking-wider text-slate-500 font-semibold">
              <tr>
                <th className="p-3">Employee</th>
                <th className="p-3">Department</th>
                <th className="p-3">Designation / Role</th>
                <th className="p-3">Reports To (Manager)</th>
                <th className="p-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {allEmployees
                .filter(
                  (emp) =>
                    !search ||
                    emp.full_name.toLowerCase().includes(search.toLowerCase()) ||
                    emp.employee_code.toLowerCase().includes(search.toLowerCase()) ||
                    (emp.job_title && emp.job_title.toLowerCase().includes(search.toLowerCase())),
                )
                .map((emp) => {
                  const manager = emp.reports_to_id ? empMap.get(emp.reports_to_id) : null;
                  return (
                    <tr key={emp.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="p-3">
                        <div className="flex items-center gap-2.5">
                          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">
                            {initials(emp.full_name)}
                          </span>
                          <div>
                            <div className="font-medium text-slate-900">{emp.full_name}</div>
                            <div className="text-xs text-slate-400">{emp.employee_code} · {emp.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="p-3 text-slate-600">
                        <Badge tone="grey">{rawTree.find((n) => n.id === emp.id)?.department_name || "General"}</Badge>
                      </td>
                      <td className="p-3">
                        <div className="font-medium text-slate-800 text-xs">{emp.job_title || "No Title"}</div>
                        <div className="flex flex-wrap gap-1 mt-0.5">
                          {emp.roles.map((r) => (
                            <Badge key={r} tone={r === "owner" ? "orange" : r === "ceo" ? "purple" : r === "manager" ? "indigo" : "grey"}>
                              {r}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="p-3">
                        {manager ? (
                          <div className="flex items-center gap-2 text-xs">
                            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-700">
                              {initials(manager.full_name)}
                            </span>
                            <span className="font-medium text-slate-800">{manager.full_name}</span>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400 italic">None (Top Level / Executive)</span>
                        )}
                      </td>
                      <td className="p-3 text-right">
                        <Button
                          variant="outline"
                          className="text-xs py-1 px-2.5"
                          onClick={() =>
                            setEditingEmployee({
                              id: emp.id,
                              full_name: emp.full_name,
                              current_manager_id: emp.reports_to_id,
                            })
                          }
                        >
                          Change Manager
                        </Button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </Card>
      )}

      {/* Edit Manager Modal */}
      {editingEmployee && (
        <ChangeManagerModal
          employee={editingEmployee}
          companyEmployees={allEmployees}
          tree={rawTree}
          onClose={() => setEditingEmployee(null)}
          onSaved={() => {
            setEditingEmployee(null);
            qc.invalidateQueries({ queryKey: ["hierarchy-tree"] });
            qc.invalidateQueries({ queryKey: ["employees"] });
          }}
        />
      )}
    </>
  );
}

/** Recursive Tree Node Item */
function TreeNodeItem({
  node,
  expandedIds,
  onToggle,
  searchQuery,
  onEditManager,
  depth = 0,
}: {
  node: HierarchyNode;
  expandedIds: Set<number>;
  onToggle: (id: number) => void;
  searchQuery: string;
  onEditManager: (node: HierarchyNode) => void;
  depth?: number;
}) {
  const hasChildren = node.children && node.children.length > 0;
  // If search matches, keep expanded
  const matchesSearch =
    searchQuery &&
    (node.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (node.job_title && node.job_title.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (node.department_name && node.department_name.toLowerCase().includes(searchQuery.toLowerCase())));

  const isExpanded = expandedIds.has(node.id) || !!searchQuery;

  const roles = node.roles || [];
  const isOwner = roles.includes("owner");
  const isCeo = roles.includes("ceo");
  const isManager = roles.includes("manager");
  const isHead = roles.includes("department_head");

  return (
    <div className={`space-y-2 ${depth > 0 ? "ml-6 border-l-2 border-slate-200/80 pl-4" : ""}`}>
      <Card
        className={`p-3.5 transition-all hover:border-indigo-300 hover:shadow-sm ${
          matchesSearch ? "border-indigo-500 bg-indigo-50/30" : "bg-white"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {hasChildren ? (
              <button
                type="button"
                onClick={() => onToggle(node.id)}
                className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors"
                title={isExpanded ? "Collapse" : "Expand"}
              >
                {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              </button>
            ) : (
              <div className="w-7 text-center text-slate-300">·</div>
            )}

            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-indigo-700 text-sm font-bold text-white shadow-sm">
              {initials(node.full_name)}
            </div>

            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900 text-sm">{node.full_name}</span>
                {node.employee_code && (
                  <span className="text-[11px] font-mono text-slate-400">({node.employee_code})</span>
                )}
                {isOwner && <Badge tone="orange">Owner</Badge>}
                {isCeo && <Badge tone="purple">CEO</Badge>}
                {isManager && <Badge tone="indigo">Manager</Badge>}
                {isHead && <Badge tone="blue">Head</Badge>}
              </div>

              <div className="flex flex-wrap items-center gap-2 mt-0.5 text-xs text-slate-500">
                <span className="font-medium text-slate-700">{node.job_title || "General Staff"}</span>
                {node.department_name && (
                  <>
                    <span>•</span>
                    <span className="text-slate-500">{node.department_name}</span>
                  </>
                )}
                {node.email && (
                  <>
                    <span>•</span>
                    <span className="text-slate-400">{node.email}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {hasChildren && (
              <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 border border-indigo-100">
                {node.children.length} {node.children.length === 1 ? "direct report" : "direct reports"}
              </span>
            )}
            <Button
              variant="outline"
              className="text-xs py-1 px-3 text-slate-700 hover:border-indigo-300 hover:text-indigo-600"
              onClick={() => onEditManager(node)}
            >
              Change Manager
            </Button>
          </div>
        </div>
      </Card>

      {hasChildren && isExpanded && (
        <div className="space-y-2 pt-1">
          {node.children.map((child) => (
            <TreeNodeItem
              key={child.id}
              node={child}
              expandedIds={expandedIds}
              onToggle={onToggle}
              searchQuery={searchQuery}
              onEditManager={onEditManager}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Change Manager Modal */
function ChangeManagerModal({
  employee,
  companyEmployees,
  tree,
  onClose,
  onSaved,
}: {
  employee: { id: number; full_name: string; current_manager_id: number | null };
  companyEmployees: EmployeeItem[];
  tree: HierarchyNode[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [reportsToId, setReportsToId] = useState<string>(
    employee.current_manager_id ? String(employee.current_manager_id) : "",
  );

  // Subtree IDs that would cause a reporting cycle
  const cycleForbiddenIds = useMemo(() => {
    return getSubtreeIds(tree, employee.id);
  }, [tree, employee.id]);

  const saveMutation = useMutation({
    mutationFn: () =>
      api("/hierarchy/relationships", {
        method: "POST",
        body: {
          employee_id: employee.id,
          reports_to_id: reportsToId ? Number(reportsToId) : null,
        },
      }),
    onSuccess: onSaved,
  });

  // Eligible managers: exclude self and anyone in employee's subtree
  const eligibleManagers = companyEmployees.filter((e) => !cycleForbiddenIds.has(e.id));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-md p-6 shadow-2xl">
        <h2 className="text-base font-semibold text-slate-900">Set Direct Manager</h2>
        <p className="mt-1 text-xs text-slate-500">
          Configure who <strong className="text-slate-800">{employee.full_name}</strong> reports to directly.
        </p>

        <div className="mt-5 space-y-4">
          <Field label="Reports To (Direct Manager)">
            <Select
              value={reportsToId}
              onChange={(e) => setReportsToId(e.target.value)}
              className="w-full text-sm font-medium"
            >
              <option value="">None (Top Level / Direct to Owner or Executive)</option>
              {eligibleManagers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.full_name} {m.job_title ? `— ${m.job_title}` : ""} ({m.employee_code})
                </option>
              ))}
            </Select>
          </Field>

          {cycleForbiddenIds.size > 1 && (
            <p className="text-[11px] text-amber-700 bg-amber-50 p-2.5 rounded-lg border border-amber-200">
              Note: Direct and indirect subordinates of {employee.full_name} are excluded from this list to prevent circular reporting lines.
            </p>
          )}

          <ErrorNote error={saveMutation.error} />
        </div>

        <div className="mt-6 flex items-center justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={saveMutation.isPending}>
            Cancel
          </Button>
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            {saveMutation.isPending ? "Saving..." : "Save Reporting Line"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
