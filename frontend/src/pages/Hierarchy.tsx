import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  GitFork,
  Layers,
  Network,
  Search,
  UserPlus,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import {
  ChangeManagerModal,
  OrgHierarchyTree,
  initials,
  type EmployeeItem,
  type HierarchyNode,
} from "@/components/OrgHierarchyTree";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Company = {
  id: number;
  name: string;
  code: string;
  logo_url?: string | null;
  is_active: boolean;
};

export function Hierarchy() {
  const { me, can } = useAuth();
  const isOwner = Boolean(me?.roles?.includes("owner"));
  const isCEO = Boolean(me?.roles?.includes("ceo"));
  const canManageHierarchy = can("hierarchy.manage");

  const [activeTab, setActiveTab] = useState<"tree" | "table">("tree");
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>("");
  const [search, setSearch] = useState("");
  const [editingEmployee, setEditingEmployee] = useState<{
    id: number;
    full_name: string;
    current_manager_id: number | null;
  } | null>(null);

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

  // Load employees for company (for table view)
  const employeesQuery = useQuery({
    queryKey: ["employees", "company", cidNum],
    queryFn: () =>
      api<{ items: EmployeeItem[]; total: number }>("/employees", {
        params: { company_id: cidNum, page_size: 200, status: "active" },
      }),
    enabled: !!cidNum || companies.length === 0,
  });

  const treeQuery = useQuery({
    queryKey: ["hierarchy-tree", cidNum],
    queryFn: () =>
      api<HierarchyNode[]>("/hierarchy/tree", {
        params: cidNum ? { company_id: cidNum } : undefined,
      }),
    enabled: !!cidNum || companies.length === 0,
  });

  const allEmployees = employeesQuery.data?.items || [];
  const rawTree = treeQuery.data || [];

  // Map employee ID -> Manager for table view lookups
  const empMap = useMemo(() => {
    const map = new Map<number, EmployeeItem>();
    for (const e of allEmployees) {
      map.set(e.id, e);
    }
    return map;
  }, [allEmployees]);

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
                to="/employees?add=1"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 transition-colors"
              >
                <UserPlus size={16} /> Add Employee
              </Link>
            )}
            {can("employee.manage") && (
              <Link
                to="/role-emails"
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
              >
                <span>✉️</span> Invite by Email
              </Link>
            )}
            {can("department.manage") && (
              <Link
                to="/departments"
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors"
              >
                <Building2 size={16} /> Departments
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
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Company:
                </span>
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
                  activeTab === "tree"
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Network size={14} /> Org Chart (Hold & Drag)
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("table")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-all ${
                  activeTab === "table"
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Layers size={14} /> Reporting Lines Table
              </button>
            </div>
          </div>
        </div>
      </Card>

      {/* Main Content Area */}
      {companiesQuery.isLoading ? (
        <Card className="p-12 flex justify-center items-center">
          <Spinner />
        </Card>
      ) : activeTab === "tree" ? (
        <Card className="p-5 bg-white border border-slate-200/80 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Interactive Organization Chart
              </h2>
              <p className="text-xs text-slate-500">
                Hold and move any employee card onto another team member to reassign their manager. Drop onto the top zone to make them a top-level report.
              </p>
            </div>
          </div>
          <OrgHierarchyTree
            companyId={cidNum}
            canManage={canManageHierarchy}
            showControls={true}
          />
        </Card>
      ) : (
        <Card className="overflow-x-auto p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-slate-900">
              Reporting Lines Directory
            </h2>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <Input
                placeholder="Search person or title..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-56 pl-8 text-xs py-1.5"
              />
            </div>
          </div>

          {employeesQuery.isLoading ? (
            <div className="p-8 flex justify-center"><Spinner /></div>
          ) : allEmployees.length === 0 ? (
            <EmptyState
              icon={<GitFork size={28} className="text-slate-400" />}
              title="No employees found for this company"
              hint="Add employees directly or invite them via email."
            />
          ) : (
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
                      (emp.job_title &&
                        emp.job_title.toLowerCase().includes(search.toLowerCase())),
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
                              <div className="text-xs text-slate-400">
                                {emp.employee_code} · {emp.email}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="p-3 text-slate-600">
                          <Badge tone="grey">
                            {rawTree.find((n) => n.id === emp.id)?.department_name || "General"}
                          </Badge>
                        </td>
                        <td className="p-3">
                          <div className="font-medium text-slate-800 text-xs">
                            {emp.job_title || "No Title"}
                          </div>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {emp.roles.map((r) => (
                              <Badge
                                key={r}
                                tone={
                                  r === "owner"
                                    ? "orange"
                                    : r === "ceo"
                                    ? "purple"
                                    : r === "manager"
                                    ? "indigo"
                                    : "grey"
                                }
                              >
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
                              <span className="font-medium text-slate-800">
                                {manager.full_name}
                              </span>
                            </div>
                          ) : (
                            <span className="text-xs text-slate-400 italic">
                              None (Top Level / Executive)
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-right">
                          {canManageHierarchy && (
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
                          )}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          )}
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
            employeesQuery.refetch();
            treeQuery.refetch();
          }}
        />
      )}
    </>
  );
}
