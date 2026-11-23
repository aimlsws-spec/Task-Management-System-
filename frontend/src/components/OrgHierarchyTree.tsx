import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Crown,
  GitFork,
  GripVertical,
  Info,
  Search,
  UserPlus,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export type HierarchyNode = {
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

export type EmployeeItem = {
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

export function initials(name?: string | null) {
  const parts = (name ?? "?").split(/[\s@.]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[1][0] : "")).toUpperCase();
}

/** Collect all employee IDs in the subtree under `nodeId` (including `nodeId` itself) to prevent cycles */
export function getSubtreeIds(nodes: HierarchyNode[], targetId: number): Set<number> {
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

export interface OrgHierarchyTreeProps {
  companyId?: number;
  canManage?: boolean;
  compact?: boolean;
  showControls?: boolean;
  onAddEmployeeClick?: () => void;
}

export function OrgHierarchyTree({
  companyId,
  canManage: canManageProp,
  compact = false,
  showControls = true,
  onAddEmployeeClick,
}: OrgHierarchyTreeProps) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const canManage = canManageProp ?? can("hierarchy.manage");

  const [search, setSearch] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [draggingNode, setDraggingNode] = useState<HierarchyNode | null>(null);
  const [dragOverTargetId, setDragOverTargetId] = useState<number | "top" | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [editingEmployee, setEditingEmployee] = useState<{ id: number; full_name: string; current_manager_id: number | null } | null>(null);

  // Load tree
  const treeQuery = useQuery({
    queryKey: ["hierarchy-tree", companyId],
    queryFn: () => api<HierarchyNode[]>("/hierarchy/tree", { params: companyId ? { company_id: companyId } : undefined }),
  });

  // Load employees for company (for manager reassignment modal fallback)
  const employeesQuery = useQuery({
    queryKey: ["employees", "company", companyId],
    queryFn: () =>
      api<{ items: EmployeeItem[]; total: number }>("/employees", {
        params: { company_id: companyId, page_size: 200, status: "active" },
      }),
  });

  const rawTree = treeQuery.data || [];
  const allEmployees = employeesQuery.data?.items || [];

  // Subtree of the dragged node (to prevent cycles client-side)
  const cycleForbiddenIds = useMemo(() => {
    if (!draggingNode) return new Set<number>();
    return getSubtreeIds(rawTree, draggingNode.id);
  }, [rawTree, draggingNode]);

  // Mutation to reassign manager via drag-and-drop
  const reassignMutation = useMutation({
    mutationFn: ({
      employeeId,
      reportsToId,
    }: {
      employeeId: number;
      reportsToId: number | null;
      draggedName: string;
      targetName: string;
    }) =>
      api("/hierarchy/relationships", {
        method: "POST",
        body: { employee_id: employeeId, reports_to_id: reportsToId },
      }),
    onSuccess: (_data, variables) => {
      setFeedback({
        type: "success",
        text: `Reporting line updated: ${variables.draggedName} now reports to ${variables.targetName}.`,
      });
      qc.invalidateQueries({ queryKey: ["hierarchy-tree"] });
      qc.invalidateQueries({ queryKey: ["employees"] });
      // Auto-clear success banner after 6s
      setTimeout(() => {
        setFeedback((prev) => (prev?.type === "success" ? null : prev));
      }, 6000);
    },
    onError: (err: any) => {
      setFeedback({
        type: "error",
        text: err?.message || "Failed to update reporting line. Ensure you have permissions for this company.",
      });
    },
  });

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

  // Drag and drop handlers
  const handleDragStart = (e: React.DragEvent, node: HierarchyNode) => {
    if (!canManage) return;
    e.dataTransfer.setData("text/plain", String(node.id));
    e.dataTransfer.effectAllowed = "move";
    setDraggingNode(node);
  };

  const handleDragEnd = () => {
    setDraggingNode(null);
    setDragOverTargetId(null);
  };

  const handleDragOver = (e: React.DragEvent, targetId: number | "top") => {
    if (!draggingNode || !canManage) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverTargetId !== targetId) {
      setDragOverTargetId(targetId);
    }
  };

  const handleDrop = (targetNode: HierarchyNode | null) => {
    setDragOverTargetId(null);
    if (!draggingNode || !canManage) return;
    const dragged = draggingNode;
    setDraggingNode(null);

    // Dropped on Top-Level Executive zone
    if (targetNode === null) {
      if (dragged.reports_to_id === null) {
        setFeedback({
          type: "info",
          text: `${dragged.full_name} is already at the top level (reports to Owner/CEO).`,
        });
        return;
      }
      reassignMutation.mutate({
        employeeId: dragged.id,
        reportsToId: null,
        draggedName: dragged.full_name,
        targetName: "Top Level (Reports to Owner/CEO)",
      });
      return;
    }

    // Dropped on self
    if (targetNode.id === dragged.id) {
      return;
    }

    // Dropped on current manager
    if (dragged.reports_to_id === targetNode.id) {
      setFeedback({
        type: "info",
        text: `${dragged.full_name} already reports directly to ${targetNode.full_name}.`,
      });
      return;
    }

    // Dropped on subordinate (cycle prevention)
    if (cycleForbiddenIds.has(targetNode.id)) {
      setFeedback({
        type: "error",
        text: `Cannot set ${dragged.full_name} to report to ${targetNode.full_name} because ${targetNode.full_name} is in their direct reporting chain (cycle prohibited).`,
      });
      return;
    }

    // Valid drop
    reassignMutation.mutate({
      employeeId: dragged.id,
      reportsToId: targetNode.id,
      draggedName: dragged.full_name,
      targetName: targetNode.full_name,
    });
  };

  return (
    <div className="space-y-4">
      {/* Optional Top Controls Bar */}
      {showControls && (
        <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-slate-100">
          <div className="flex flex-wrap items-center gap-2">
            {canManage && (
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 border border-indigo-100">
                <GripVertical size={13} className="text-indigo-500" />
                Hold & Drag enabled: move any card onto a manager
              </span>
            )}
            {rawTree.length > 0 && (
              <Button variant="outline" className="text-xs py-1 px-3" onClick={handleToggleExpandAll}>
                {expandedIds.size > 0 ? "Collapse All" : "Expand All"}
              </Button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <Input
                placeholder="Search person or title..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-48 pl-8 text-xs py-1.5"
              />
            </div>
            {onAddEmployeeClick && (
              <Button onClick={onAddEmployeeClick} className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs py-1.5 px-3">
                <UserPlus size={14} className="mr-1" /> Add Employee
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Feedback Banner */}
      {feedback && (
        <div
          className={`flex items-center justify-between rounded-xl p-3 text-xs font-medium border shadow-sm transition-all ${
            feedback.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : feedback.type === "error"
              ? "bg-red-50 border-red-200 text-red-800"
              : "bg-blue-50 border-blue-200 text-blue-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.type === "success" ? (
              <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            ) : feedback.type === "error" ? (
              <AlertCircle size={16} className="text-red-600 shrink-0" />
            ) : (
              <Info size={16} className="text-blue-600 shrink-0" />
            )}
            <span>{feedback.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-slate-400 hover:text-slate-600 p-0.5 rounded transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Reassigning Loading Indicator */}
      {reassignMutation.isPending && (
        <div className="flex items-center justify-center gap-2 p-2 rounded-lg bg-indigo-50 border border-indigo-200 text-xs text-indigo-700 font-semibold animate-pulse">
          <Spinner /> Updating reporting hierarchy…
        </div>
      )}

      {/* Top-Level Executive Drop Zone */}
      {canManage && (
        <div
          onDragOver={(e) => handleDragOver(e, "top")}
          onDragLeave={() => {
            if (dragOverTargetId === "top") setDragOverTargetId(null);
          }}
          onDrop={(e) => {
            e.preventDefault();
            handleDrop(null);
          }}
          className={`flex items-center justify-center gap-2 rounded-xl p-3 border-2 border-dashed transition-all ${
            dragOverTargetId === "top"
              ? "border-amber-500 bg-amber-100/90 text-amber-900 font-bold scale-[1.01] shadow-md ring-4 ring-amber-200/60"
              : draggingNode
              ? "border-amber-300 bg-amber-50/70 text-amber-800 animate-pulse"
              : "border-slate-300/80 bg-slate-50/70 text-slate-500 hover:border-slate-400"
          }`}
        >
          <Crown size={17} className={dragOverTargetId === "top" ? "text-amber-700 animate-bounce" : "text-amber-500"} />
          <span className="text-xs font-semibold">
            {dragOverTargetId === "top"
              ? `Release to make ${draggingNode?.full_name} Top-Level (Reports to Owner/Executive)`
              : draggingNode
              ? `Drop ${draggingNode.full_name} here to make Top-Level (No Manager)`
              : "Top-Level Drop Zone: Drag and drop any employee here to report directly to Owner / CEO"}
          </span>
        </div>
      )}

      {/* Tree Content */}
      {treeQuery.isLoading ? (
        <Card className="p-8 flex justify-center items-center">
          <Spinner />
        </Card>
      ) : rawTree.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={<GitFork size={28} className="text-slate-400" />}
            title="No hierarchy defined for this company"
            hint="Add employees or assign reporting lines to build the organizational tree."
          />
        </Card>
      ) : (
        <div className={`space-y-3 ${compact ? "max-h-[500px] overflow-y-auto pr-1" : ""}`}>
          {rawTree.map((rootNode) => (
            <TreeNodeCard
              key={rootNode.id}
              node={rootNode}
              expandedIds={expandedIds}
              onToggle={toggleNode}
              searchQuery={search}
              canManage={canManage}
              draggingNode={draggingNode}
              dragOverTargetId={dragOverTargetId}
              cycleForbiddenIds={cycleForbiddenIds}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
              onDragOver={handleDragOver}
              onDragLeave={(id) => {
                if (dragOverTargetId === id) setDragOverTargetId(null);
              }}
              onDrop={handleDrop}
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
      )}

      {/* Change Manager Modal (Accessible fallback) */}
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
    </div>
  );
}

/** Individual Tree Node Card with Drag-and-Drop and Recursive Children */
function TreeNodeCard({
  node,
  expandedIds,
  onToggle,
  searchQuery,
  canManage,
  draggingNode,
  dragOverTargetId,
  cycleForbiddenIds,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDragLeave,
  onDrop,
  onEditManager,
  depth = 0,
}: {
  node: HierarchyNode;
  expandedIds: Set<number>;
  onToggle: (id: number) => void;
  searchQuery: string;
  canManage: boolean;
  draggingNode: HierarchyNode | null;
  dragOverTargetId: number | "top" | null;
  cycleForbiddenIds: Set<number>;
  onDragStart: (e: React.DragEvent, node: HierarchyNode) => void;
  onDragEnd: () => void;
  onDragOver: (e: React.DragEvent, id: number) => void;
  onDragLeave: (id: number) => void;
  onDrop: (node: HierarchyNode) => void;
  onEditManager: (node: HierarchyNode) => void;
  depth?: number;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expandedIds.has(node.id) || !!searchQuery;

  // Search match highlighting
  const matchesSearch =
    searchQuery &&
    (node.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (node.job_title && node.job_title.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (node.department_name && node.department_name.toLowerCase().includes(searchQuery.toLowerCase())));

  // Drag and drop states for this node
  const isSelf = draggingNode?.id === node.id;
  const isCycle = draggingNode ? cycleForbiddenIds.has(node.id) : false;
  const isCurrentManager = draggingNode?.reports_to_id === node.id;
  const isTargeted = dragOverTargetId === node.id;

  const roles = node.roles || [];
  const isOwner = roles.includes("owner");
  const isCeo = roles.includes("ceo");
  const isManager = roles.includes("manager");
  const isHead = roles.includes("department_head");
  const isSubHead = roles.includes("sub_head");

  // Border & background based on drag interaction
  let dragStyle = "bg-white border-slate-200/80 hover:border-indigo-300 hover:shadow-sm";
  if (isSelf) {
    dragStyle = "opacity-40 border-2 border-dashed border-indigo-400 bg-indigo-50/30 scale-[0.99]";
  } else if (isTargeted) {
    if (isCycle) {
      dragStyle = "border-2 border-red-500 bg-red-50/90 ring-4 ring-red-200/60 shadow-lg scale-[1.01]";
    } else if (isCurrentManager) {
      dragStyle = "border-2 border-slate-400 bg-slate-100 ring-4 ring-slate-200 shadow-md";
    } else {
      dragStyle = "border-2 border-indigo-600 bg-indigo-50/90 ring-4 ring-indigo-200/80 shadow-lg scale-[1.01]";
    }
  } else if (matchesSearch) {
    dragStyle = "border-indigo-500 bg-indigo-50/30";
  }

  return (
    <div className={`space-y-2 ${depth > 0 ? "ml-6 border-l-2 border-slate-200/80 pl-4" : ""}`}>
      <div
        draggable={canManage && !isSelf}
        onDragStart={(e) => onDragStart(e, node)}
        onDragEnd={onDragEnd}
        onDragOver={(e) => onDragOver(e, node.id)}
        onDragLeave={() => onDragLeave(node.id)}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onDrop(node);
        }}
        className={`rounded-xl border p-3.5 transition-all ${dragStyle}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            {/* Drag Handle Grip */}
            {canManage && (
              <div
                className="cursor-grab active:cursor-grabbing text-slate-300 hover:text-indigo-600 p-0.5 rounded transition-colors"
                title="Hold and drag to reassign reporting line"
              >
                <GripVertical size={16} />
              </div>
            )}

            {/* Expand / Collapse Toggle */}
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

            {/* Avatar */}
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-indigo-700 text-xs font-bold text-white shadow-sm">
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
                {isSubHead && <Badge tone="grey">SubHead</Badge>}
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

          <div className="flex items-center gap-2.5">
            {/* Visual drop indicator badge when hovered during drag */}
            {isTargeted && draggingNode && (
              <div className="animate-pulse">
                {isCycle ? (
                  <span className="rounded-lg bg-red-100 px-2 py-1 text-xs font-bold text-red-700 border border-red-300">
                    🚫 Prohibited: Subordinate of {draggingNode.full_name}
                  </span>
                ) : isCurrentManager ? (
                  <span className="rounded-lg bg-slate-200 px-2 py-1 text-xs font-medium text-slate-700">
                    ℹ️ Current Manager
                  </span>
                ) : (
                  <span className="rounded-lg bg-indigo-600 px-2.5 py-1 text-xs font-bold text-white shadow-sm">
                    📥 Drop to make {node.full_name} manager
                  </span>
                )}
              </div>
            )}

            {hasChildren && !isTargeted && (
              <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 border border-indigo-100">
                {node.children.length} {node.children.length === 1 ? "direct report" : "direct reports"}
              </span>
            )}

            {canManage && (
              <Button
                variant="outline"
                className="text-xs py-1 px-2.5 text-slate-700 hover:border-indigo-300 hover:text-indigo-600"
                onClick={() => onEditManager(node)}
              >
                Change Manager
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Recursive Direct Reports */}
      {hasChildren && isExpanded && (
        <div className="space-y-2 pt-1">
          {node.children.map((child) => (
            <TreeNodeCard
              key={child.id}
              node={child}
              expandedIds={expandedIds}
              onToggle={onToggle}
              searchQuery={searchQuery}
              canManage={canManage}
              draggingNode={draggingNode}
              dragOverTargetId={dragOverTargetId}
              cycleForbiddenIds={cycleForbiddenIds}
              onDragStart={onDragStart}
              onDragEnd={onDragEnd}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onEditManager={onEditManager}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Change Manager Modal (Accessible fallback) */
export function ChangeManagerModal({
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
