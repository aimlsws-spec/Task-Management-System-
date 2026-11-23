"""Shared employees/departments across companies, multiple department heads/subheads, and project priority

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-23 12:55:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create department_heads table for multiple heads & subheads in a department
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS department_heads (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            department_id BIGINT NOT NULL,
            employee_id BIGINT NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'head',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_dept_emp_role (department_id, employee_id, role),
            CONSTRAINT fk_dept_head_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
            CONSTRAINT fk_dept_head_emp FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))

    # Backfill existing department heads and sub-heads
    conn.execute(sa.text("""
        INSERT IGNORE INTO department_heads (department_id, employee_id, role, created_at)
        SELECT id, head_employee_id, 'head', UTC_TIMESTAMP() FROM departments WHERE head_employee_id IS NOT NULL;
    """))
    conn.execute(sa.text("""
        INSERT IGNORE INTO department_heads (department_id, employee_id, role, created_at)
        SELECT id, sub_head_employee_id, 'sub_head', UTC_TIMESTAMP() FROM departments WHERE sub_head_employee_id IS NOT NULL;
    """))

    # 2. Create employee_companies join table for employees working across multiple companies
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS employee_companies (
            employee_id BIGINT NOT NULL,
            company_id BIGINT NOT NULL,
            PRIMARY KEY (employee_id, company_id),
            CONSTRAINT fk_emp_comp_emp FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            CONSTRAINT fk_emp_comp_comp FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    conn.execute(sa.text("""
        INSERT IGNORE INTO employee_companies (employee_id, company_id)
        SELECT id, company_id FROM employees WHERE company_id IS NOT NULL;
    """))

    # 3. Create department_companies join table for departments shared across multiple companies
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS department_companies (
            department_id BIGINT NOT NULL,
            company_id BIGINT NOT NULL,
            PRIMARY KEY (department_id, company_id),
            CONSTRAINT fk_dept_comp_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
            CONSTRAINT fk_dept_comp_comp FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    conn.execute(sa.text("""
        INSERT IGNORE INTO department_companies (department_id, company_id)
        SELECT id, company_id FROM departments WHERE company_id IS NOT NULL;
    """))

    # 4. Modify company_id on employees and departments to be nullable (NULL = shared across all companies)
    conn.execute(sa.text("ALTER TABLE employees MODIFY company_id BIGINT NULL;"))
    conn.execute(sa.text("ALTER TABLE departments MODIFY company_id BIGINT NULL;"))

    # 5. Add priority and special_note to projects table if not already present
    try:
        conn.execute(sa.text("ALTER TABLE projects ADD COLUMN priority VARCHAR(20) NULL DEFAULT 'medium';"))
    except Exception:
        pass
    try:
        conn.execute(sa.text("ALTER TABLE projects ADD COLUMN special_note TEXT NULL;"))
    except Exception:
        pass


def downgrade() -> None:
    conn = op.get_bind()
    try:
        conn.execute(sa.text("ALTER TABLE projects DROP COLUMN special_note;"))
    except Exception:
        pass
    try:
        conn.execute(sa.text("ALTER TABLE projects DROP COLUMN priority;"))
    except Exception:
        pass
    conn.execute(sa.text("DROP TABLE IF EXISTS department_companies;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS employee_companies;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS department_heads;"))
