import { Navigate, Route, Routes } from "react-router-dom";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ChangePassword } from "@/pages/ChangePassword";
import { AdminNotifications } from "@/pages/AdminNotifications";
import { Dashboard } from "@/pages/Dashboard";
import { Notifications } from "@/pages/Notifications";
import { Blockers } from "@/pages/Blockers";
import { DelayReviews } from "@/pages/DelayReviews";
import { Departments } from "@/pages/Departments";
import { Employees } from "@/pages/Employees";
import { ForgotPassword } from "@/pages/ForgotPassword";
import { Login } from "@/pages/Login";
import { NewTask } from "@/pages/NewTask";
import { Onboarding } from "@/pages/Onboarding";
import { ProjectDetail } from "@/pages/ProjectDetail";
import { Projects } from "@/pages/Projects";
import { TaskDetail } from "@/pages/TaskDetail";
import { Tasks } from "@/pages/Tasks";
import { WorkloadPage } from "@/pages/Workload";
import { Roles } from "@/pages/Roles";
import { RoleEmails } from "@/pages/RoleEmails";
import { ReportsPage } from "@/pages/Reports";
import { AuditLogPage } from "@/pages/AuditLog";
import { AdminPanel } from "@/pages/AdminPanel";
import { Signup } from "@/pages/Signup";
import { AppShell } from "./AppShell";

function Protected({ children, perm }: { children: React.ReactNode; perm?: string }) {
  const { can } = useAuth();
  if (perm && !can(perm)) return <p className="text-sm text-slate-500">You do not have access to this page.</p>;
  return <>{children}</>;
}

export function App() {
  const { status, me } = useAuth();
  if (status === "loading") return <Spinner />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      {status === "anon" ? (
        <Route path="*" element={<Navigate to="/login" replace />} />
      ) : me?.user.must_change_password ? (
        <Route path="*" element={<ChangePassword />} />
      ) : me?.employee?.status === "pending_setup" ? (
        // New self-registered employee: must choose department + designation before anything else.
        <Route path="*" element={<Onboarding />} />
      ) : (
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="tasks" element={<Protected perm="task.view"><Tasks /></Protected>} />
          <Route path="tasks/new" element={<Protected perm="task.create"><NewTask /></Protected>} />
          <Route path="tasks/:id" element={<Protected perm="task.view"><TaskDetail /></Protected>} />
          <Route path="blockers" element={<Protected perm="blocker.view"><Blockers /></Protected>} />
          <Route path="delays" element={<Protected perm="delay.review"><DelayReviews /></Protected>} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="admin/notifications" element={<Protected perm="notification.rules.manage"><AdminNotifications /></Protected>} />
          <Route path="workload" element={<Protected perm="task.assign"><WorkloadPage /></Protected>} />
          <Route path="reports" element={<Protected perm="report.view"><ReportsPage /></Protected>} />
          <Route path="audit" element={<Protected perm="audit.view"><AuditLogPage /></Protected>} />
          <Route path="projects" element={<Protected perm="task.view"><Projects /></Protected>} />
          <Route path="projects/:id" element={<Protected perm="task.view"><ProjectDetail /></Protected>} />
          {/* Administration (Admin and Owner access; API enforces permissions) */}
          <Route path="admin" element={<Protected perm="employee.manage"><AdminPanel /></Protected>} />
          <Route path="employees" element={<Protected perm="employee.view"><Employees /></Protected>} />
          <Route path="departments" element={<Protected perm="department.manage"><Departments /></Protected>} />
          <Route path="role-emails" element={<Protected perm="employee.manage"><RoleEmails /></Protected>} />
          <Route path="roles" element={<Protected perm="role.manage"><Roles /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      )}
    </Routes>
  );
}
