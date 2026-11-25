import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_dir))

import app.models_registry
from app.core.db import SessionLocal
from app.core.security import hash_password, verify_password
from app.modules.auth.models import User
from app.modules.org.models import Employee, Department, Company
from app.modules.rbac.models import UserRole, Role
from app.modules.tasks.models import Task, Project
from sqlalchemy import text

def clean_database():
    target_email = "krishadave485@gmail.com"
    target_pwd = "Bmk@123$123"

    print("Beginning database cleanup...")
    with SessionLocal() as db:
        # Disable foreign key checks for clean truncation/deletion
        db.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

        # 1. Clear all task and project related tables
        task_tables = [
            "comment_mentions",
            "task_comments",
            "task_blocker_events",
            "task_blockers",
            "task_attachments",
            "task_delay_reviews",
            "task_delay_reasons",
            "deadline_extension_requests",
            "task_deadline_history",
            "task_time_corrections",
            "timer_checkins",
            "task_time_logs",
            "task_reverts",
            "task_verifications",
            "task_updates",
            "task_status_history",
            "task_assignments",
            "task_head_ownership",
            "task_heads",
            "task_qa_members",
            "task_completion_assurances",
            "reminder_log",
            "project_points",
            "tasks",
            "project_heads",
            "project_members",
            "project_qa_members",
            "projects",
        ]
        for tbl in task_tables:
            print(f"Clearing {tbl}...")
            db.execute(text(f"DELETE FROM `{tbl}`;"))
            try:
                db.execute(text(f"ALTER TABLE `{tbl}` AUTO_INCREMENT = 1;"))
            except Exception:
                pass

        # 2. Clear department leaders pointing to demo employees
        print("Resetting department head pointers...")
        db.execute(text("UPDATE departments SET head_employee_id = NULL, sub_head_employee_id = NULL, qa_employee_id = NULL;"))
        db.execute(text("DELETE FROM department_heads;"))
        db.execute(text("DELETE FROM manager_departments;"))
        db.execute(text("DELETE FROM reporting_relationships;"))
        db.execute(text("DELETE FROM employee_leaves;"))

        # 3. Clear logs, tokens, notifications, invites
        print("Clearing temporary auth & notification records...")
        db.execute(text("DELETE FROM role_invites;"))
        db.execute(text("DELETE FROM email_logs;"))
        db.execute(text("ALTER TABLE email_logs AUTO_INCREMENT = 1;"))
        db.execute(text("DELETE FROM notifications;"))
        db.execute(text("ALTER TABLE notifications AUTO_INCREMENT = 1;"))
        db.execute(text("DELETE FROM outbox_events;"))
        db.execute(text("ALTER TABLE outbox_events AUTO_INCREMENT = 1;"))
        db.execute(text("DELETE FROM login_otps;"))
        db.execute(text("DELETE FROM refresh_tokens;"))
        db.execute(text("DELETE FROM password_reset_tokens;"))
        db.execute(text("DELETE FROM company_ceos;"))
        db.execute(text("DELETE FROM company_knowledge;"))
        db.execute(text("DELETE FROM activity_logs;"))
        db.execute(text("ALTER TABLE activity_logs AUTO_INCREMENT = 1;"))
        db.execute(text("DELETE FROM job_failures;"))
        db.execute(text("ALTER TABLE job_failures AUTO_INCREMENT = 1;"))

        # 4. Remove fake users and employees (keep only user 1 / krishadave485@gmail.com)
        target_user = db.query(User).filter_by(email=target_email).first()
        if not target_user:
            target_user = db.query(User).get(1)
        
        target_user_id = target_user.id
        print(f"Target Owner/Admin user ID: {target_user_id} ({target_user.email})")

        # Update target user
        target_user.email = target_email
        target_user.password_hash = hash_password(target_pwd)
        target_user.must_change_password = False
        target_user.is_active = True

        # Target employee
        target_emp = db.query(Employee).filter_by(user_id=target_user_id).first()
        if target_emp:
            target_emp_id = target_emp.id
            target_emp.full_name = "Administrator"
            target_emp.job_title = "System Administrator"
            target_emp.company_id = 1
            target_emp.department_id = 1
            target_emp.status = "active"
            target_emp.can_receive_tasks = True
        else:
            target_emp_id = 1

        # Delete all other user roles, employee companies, employees, and users
        print("Removing other users and employees...")
        db.execute(text(f"DELETE FROM notification_preferences WHERE user_id != {target_user_id};"))
        db.execute(text(f"DELETE FROM user_roles WHERE user_id != {target_user_id};"))
        db.execute(text(f"DELETE FROM employee_companies WHERE employee_id != {target_emp_id};"))
        db.execute(text(f"DELETE FROM employees WHERE id != {target_emp_id};"))
        db.execute(text(f"DELETE FROM users WHERE id != {target_user_id};"))

        # Ensure target user has both 'admin' and 'owner' roles
        owner_role = db.query(Role).filter_by(code="owner").first()
        admin_role = db.query(Role).filter_by(code="admin").first()

        existing_role_ids = {r[0] for r in db.query(UserRole.role_id).filter_by(user_id=target_user_id).all()}
        if owner_role and owner_role.id not in existing_role_ids:
            db.add(UserRole(user_id=target_user_id, role_id=owner_role.id, granted_by=target_user_id))
        if admin_role and admin_role.id not in existing_role_ids:
            db.add(UserRole(user_id=target_user_id, role_id=admin_role.id, granted_by=target_user_id))

        # Re-enable foreign key checks
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        db.commit()

    print("Cleanup executed successfully. Running verification checks...")
    with SessionLocal() as db:
        users = db.query(User).all()
        print(f"Users in DB ({len(users)}):")
        for u in users:
            roles = [r[0] for r in db.query(Role.code).join(UserRole, UserRole.role_id == Role.id).filter(UserRole.user_id == u.id).all()]
            print(f" - ID: {u.id}, Email: {u.email}, Roles: {roles}, IsActive: {u.is_active}, MustChangePwd: {u.must_change_password}")
            assert u.email == target_email, f"Unexpected user: {u.email}"
            assert verify_password(target_pwd, u.password_hash), "Password verification failed!"
            assert "owner" in roles and "admin" in roles, "Owner/Admin roles missing!"

        emps = db.query(Employee).all()
        print(f"Employees in DB ({len(emps)}):")
        for e in emps:
            u_email = db.query(User.email).filter_by(id=e.user_id).scalar()
            print(f" - ID: {e.id}, FullName: {e.full_name}, Email: {u_email}, Status: {e.status}")
            assert e.user_id == target_user_id, f"Unexpected employee: {e.full_name}"

        task_count = db.query(Task).count()
        proj_count = db.query(Project).count()
        print(f"Tasks in DB: {task_count}")
        print(f"Projects in DB: {proj_count}")
        assert task_count == 0, "Tasks were not cleared!"
        assert proj_count == 0, "Projects were not cleared!"

    print("ALL VERIFICATIONS PASSED!")

if __name__ == "__main__":
    clean_database()
