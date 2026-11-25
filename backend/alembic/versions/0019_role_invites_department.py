"""Add department_id to role_invites

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-25 13:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('role_invites')]
    if 'department_id' not in cols:
        conn.execute(sa.text("""
            ALTER TABLE role_invites
            ADD COLUMN department_id BIGINT NULL,
            ADD CONSTRAINT fk_role_invites_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL;
        """))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('role_invites')]
    if 'department_id' in cols:
        conn.execute(sa.text("""
            ALTER TABLE role_invites
            DROP FOREIGN KEY fk_role_invites_dept,
            DROP COLUMN department_id;
        """))
