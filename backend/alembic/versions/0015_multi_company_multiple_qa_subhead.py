"""Multi-company architecture, multiple QA members, and department SubHead

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-23 10:20:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create companies table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS companies (
            id BIGINT NOT NULL AUTO_INCREMENT,
            name VARCHAR(150) NOT NULL,
            code VARCHAR(50) NOT NULL UNIQUE,
            logo_url VARCHAR(255) NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))

    # 2. Insert default company SeaWind Solution
    conn.execute(sa.text("""
        INSERT INTO companies (id, name, code, is_active, created_at)
        VALUES (1, 'SeaWind Solution', 'seawind', 1, UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE name = 'SeaWind Solution';
    """))

    # 3. Create company_ceos table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS company_ceos (
            company_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            granted_by_user_id BIGINT NULL,
            granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (company_id, user_id),
            CONSTRAINT fk_cceo_company FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            CONSTRAINT fk_cceo_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))

    # 4. Add company_id and sub_head_employee_id to departments
    conn.execute(sa.text("""
        ALTER TABLE departments 
        ADD COLUMN company_id BIGINT NOT NULL DEFAULT 1,
        ADD COLUMN sub_head_employee_id BIGINT NULL;
    """))
    conn.execute(sa.text("""
        ALTER TABLE departments 
        ADD CONSTRAINT fk_dept_company FOREIGN KEY (company_id) REFERENCES companies(id),
        ADD CONSTRAINT fk_dept_subhead FOREIGN KEY (sub_head_employee_id) REFERENCES employees(id);
    """))

    # 5. Add company_id to employees
    conn.execute(sa.text("""
        ALTER TABLE employees 
        ADD COLUMN company_id BIGINT NOT NULL DEFAULT 1;
    """))
    conn.execute(sa.text("""
        ALTER TABLE employees 
        ADD CONSTRAINT fk_emp_company FOREIGN KEY (company_id) REFERENCES companies(id);
    """))

    # 6. Add company_id, sub_head_employee_id, and review fields to projects
    conn.execute(sa.text("""
        ALTER TABLE projects 
        ADD COLUMN company_id BIGINT NOT NULL DEFAULT 1,
        ADD COLUMN sub_head_employee_id BIGINT NULL,
        ADD COLUMN head_reviewed_at DATETIME NULL,
        ADD COLUMN head_reviewed_by_user_id BIGINT NULL,
        ADD COLUMN head_review_note TEXT NULL;
    """))
    conn.execute(sa.text("""
        ALTER TABLE projects 
        ADD CONSTRAINT fk_proj_company FOREIGN KEY (company_id) REFERENCES companies(id),
        ADD CONSTRAINT fk_proj_subhead FOREIGN KEY (sub_head_employee_id) REFERENCES employees(id),
        ADD CONSTRAINT fk_proj_head_rev_user FOREIGN KEY (head_reviewed_by_user_id) REFERENCES users(id);
    """))

    # 7. Add company_id and sub_head_employee_id to tasks
    conn.execute(sa.text("""
        ALTER TABLE tasks 
        ADD COLUMN company_id BIGINT NOT NULL DEFAULT 1,
        ADD COLUMN sub_head_employee_id BIGINT NULL;
    """))
    conn.execute(sa.text("""
        ALTER TABLE tasks 
        ADD CONSTRAINT fk_task_company FOREIGN KEY (company_id) REFERENCES companies(id),
        ADD CONSTRAINT fk_task_subhead FOREIGN KEY (sub_head_employee_id) REFERENCES employees(id);
    """))

    # 8. Add company_id to role_invites
    conn.execute(sa.text("""
        ALTER TABLE role_invites 
        ADD COLUMN company_id BIGINT NULL;
    """))
    conn.execute(sa.text("""
        ALTER TABLE role_invites 
        ADD CONSTRAINT fk_inv_company FOREIGN KEY (company_id) REFERENCES companies(id);
    """))

    # 9. Create project_qa_members table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS project_qa_members (
            project_id BIGINT NOT NULL,
            employee_id BIGINT NOT NULL,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, employee_id),
            CONSTRAINT fk_pqa_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CONSTRAINT fk_pqa_emp FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))

    # 10. Create task_qa_members table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS task_qa_members (
            task_id BIGINT NOT NULL,
            employee_id BIGINT NOT NULL,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (task_id, employee_id),
            CONSTRAINT fk_tqa_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            CONSTRAINT fk_tqa_emp FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))

    # 11. Backfill existing QA members
    conn.execute(sa.text("""
        INSERT IGNORE INTO project_qa_members (project_id, employee_id, assigned_at)
        SELECT id, qa_employee_id, UTC_TIMESTAMP() FROM projects WHERE qa_employee_id IS NOT NULL;
    """))
    conn.execute(sa.text("""
        INSERT IGNORE INTO task_qa_members (task_id, employee_id, assigned_at)
        SELECT id, qa_employee_id, UTC_TIMESTAMP() FROM tasks WHERE qa_employee_id IS NOT NULL;
    """))

    # 12. Backfill existing CEOs into company_ceos
    conn.execute(sa.text("""
        INSERT IGNORE INTO company_ceos (company_id, user_id, granted_at)
        SELECT 1, u.id, UTC_TIMESTAMP()
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id AND r.code = 'ceo';
    """))

    # 13. Insert sub_head role (rank 40)
    conn.execute(sa.text("""
        INSERT INTO roles (id, code, name, `rank`, is_system, description)
        VALUES (7, 'sub_head', 'Department SubHead', 40, 1, 'Department SubHead: assists department head, supervises department work')
        ON DUPLICATE KEY UPDATE `rank` = 40, name = 'Department SubHead';
    """))

    # 14. Grant permissions to sub_head matching department_head
    conn.execute(sa.text("""
        INSERT IGNORE INTO role_permissions (role_id, permission_id, scope)
        SELECT r_sub.id, rp.permission_id, 'department'
        FROM roles r_sub
        CROSS JOIN roles r_head
        JOIN role_permissions rp ON rp.role_id = r_head.id
        WHERE r_sub.code = 'sub_head' AND r_head.code = 'department_head';
    """))

    # 15. Bump rbac_seed_version in system_settings
    conn.execute(sa.text("""
        INSERT INTO system_settings (`key`, `value`, `updated_at`)
        VALUES ('rbac_seed_version', '6', UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE `value` = '6', `updated_at` = UTC_TIMESTAMP();
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS task_qa_members;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS project_qa_members;"))

    conn.execute(sa.text("ALTER TABLE role_invites DROP FOREIGN KEY fk_inv_company;"))
    conn.execute(sa.text("ALTER TABLE role_invites DROP COLUMN company_id;"))

    conn.execute(sa.text("ALTER TABLE tasks DROP FOREIGN KEY fk_task_company;"))
    conn.execute(sa.text("ALTER TABLE tasks DROP FOREIGN KEY fk_task_subhead;"))
    conn.execute(sa.text("ALTER TABLE tasks DROP COLUMN company_id, DROP COLUMN sub_head_employee_id;"))

    conn.execute(sa.text("ALTER TABLE projects DROP FOREIGN KEY fk_proj_company;"))
    conn.execute(sa.text("ALTER TABLE projects DROP FOREIGN KEY fk_proj_subhead;"))
    conn.execute(sa.text("ALTER TABLE projects DROP FOREIGN KEY fk_proj_head_rev_user;"))
    conn.execute(sa.text("ALTER TABLE projects DROP COLUMN company_id, DROP COLUMN sub_head_employee_id, DROP COLUMN head_reviewed_at, DROP COLUMN head_reviewed_by_user_id, DROP COLUMN head_review_note;"))

    conn.execute(sa.text("ALTER TABLE employees DROP FOREIGN KEY fk_emp_company;"))
    conn.execute(sa.text("ALTER TABLE employees DROP COLUMN company_id;"))

    conn.execute(sa.text("ALTER TABLE departments DROP FOREIGN KEY fk_dept_company;"))
    conn.execute(sa.text("ALTER TABLE departments DROP FOREIGN KEY fk_dept_subhead;"))
    conn.execute(sa.text("ALTER TABLE departments DROP COLUMN company_id, DROP COLUMN sub_head_employee_id;"))

    conn.execute(sa.text("DROP TABLE IF EXISTS company_ceos;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS companies;"))

    conn.execute(sa.text("DELETE rp FROM role_permissions rp JOIN roles r ON r.id = rp.role_id WHERE r.code = 'sub_head';"))
    conn.execute(sa.text("DELETE FROM roles WHERE code = 'sub_head';"))

    conn.execute(sa.text("""
        INSERT INTO system_settings (`key`, `value`, `updated_at`)
        VALUES ('rbac_seed_version', '5', UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE `value` = '5', `updated_at` = UTC_TIMESTAMP();
    """))

