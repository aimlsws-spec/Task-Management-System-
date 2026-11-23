"""Multiple heads on tasks and projects

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-23 11:55:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create project_heads table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS project_heads (
            project_id BIGINT NOT NULL,
            employee_id BIGINT NOT NULL,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, employee_id),
            CONSTRAINT fk_phead_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CONSTRAINT fk_phead_emp FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))

    # 2. Create task_heads table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS task_heads (
            task_id BIGINT NOT NULL,
            employee_id BIGINT NOT NULL,
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (task_id, employee_id),
            CONSTRAINT fk_thead_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            CONSTRAINT fk_thead_emp FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))

    # 3. Backfill existing project heads and sub-heads
    conn.execute(sa.text("""
        INSERT IGNORE INTO project_heads (project_id, employee_id, assigned_at)
        SELECT id, head_employee_id, UTC_TIMESTAMP() FROM projects WHERE head_employee_id IS NOT NULL;
    """))
    conn.execute(sa.text("""
        INSERT IGNORE INTO project_heads (project_id, employee_id, assigned_at)
        SELECT id, sub_head_employee_id, UTC_TIMESTAMP() FROM projects WHERE sub_head_employee_id IS NOT NULL;
    """))

    # 4. Backfill existing task heads and sub-heads
    conn.execute(sa.text("""
        INSERT IGNORE INTO task_heads (task_id, employee_id, assigned_at)
        SELECT id, head_employee_id, UTC_TIMESTAMP() FROM tasks WHERE head_employee_id IS NOT NULL;
    """))
    conn.execute(sa.text("""
        INSERT IGNORE INTO task_heads (task_id, employee_id, assigned_at)
        SELECT id, sub_head_employee_id, UTC_TIMESTAMP() FROM tasks WHERE sub_head_employee_id IS NOT NULL;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS task_heads;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS project_heads;"))
